
from django.contrib.auth import logout, authenticate, login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Exists, OuterRef, Q
from django.http import HttpResponseRedirect, Http404, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import IntegrityError
from django.core.exceptions import PermissionDenied, ObjectDoesNotExist
import json


from .models import *
from .forms import *
from .utils import get_filter_kwargs, calculate_age, generate_post_dict, get_excluded_clauses


def index(request):
    context = {}
    if request.user.is_authenticated:

        #loading index page for employer
        if request.user.is_employer:
            my_job_postings = JobPosting.objects.filter(
                employer=request.user
                ).annotate().order_by('-date')[:10]
            notifications = ResumeToEmployerNotification.objects.filter(job_posting__in=my_job_postings).count()
            context.update({'my_job_postings': my_job_postings, 'notifications': notifications})

        # loading index page for job seeker
        elif not request.user.is_employer:
            job_postings = JobPosting.objects.exclude(is_archived=True)
            context.update({'job_postings' : job_postings})

            # job seeker has a city
            if request.user.jobseekerprofile.preferred_location:
                jobs_in_location = JobPosting.objects.filter(
                        country=request.user.jobseekerprofile.preferred_country,
                        city=request.user.jobseekerprofile.preferred_location
                        ).exclude(is_archived=True).order_by(
                        "-job_open_date"
                        ).select_related('industry')[:12]
                industries_gt0_in_location = Industry.objects.annotate(
                        cnt_jobpostings=Count('jobposting')
                        ).filter(
                        cnt_jobpostings__gt=0,
                        jobposting__country=request.user.jobseekerprofile.preferred_country,
                        jobposting__city=request.user.jobseekerprofile.preferred_location,
                        jobposting__is_archived=False,
                        )
                if jobs_in_location:
                    context.update({'jobs_in_location': jobs_in_location})
                if industries_gt0_in_location:
                    context.update({'industries_gt0_in_location': industries_gt0_in_location})
            # job seeker does not have a city
            elif not request.user.jobseekerprofile.preferred_location:
                jobs_in_location = JobPosting.objects.all().exclude(is_archived=True).order_by(
                                    "-job_open_date").select_related('industry')[:12]
                industries_gt0_in_location = Industry.objects.annotate(
                        cnt_jobpostings=Count('jobposting')
                        ).filter(
                        cnt_jobpostings__gt=0
                        )
                if jobs_in_location:
                    context.update({'jobs_in_location': jobs_in_location})
                if industries_gt0_in_location:
                    context.update({'industries_gt0_in_location': industries_gt0_in_location})
    return render(request, "hh/index.html", context)


@login_required
def job_posting_view(request, job_posting_uuid):
    context = {}
    try:
        job_posting = JobPosting.objects.annotate(
            is_liked=Exists(
                JobPosting.liked.through.objects.filter(
                    jobposting_id=OuterRef('pk'), user=request.user
                )
            )
        ).get(id=job_posting_uuid)
    except ObjectDoesNotExist:
        raise Http404

    #add resumes and check like only if request.user is job seeker
    if not request.user.is_employer:
        resumes = Resume.objects.filter(user=request.user)
        resume_sent = ResumeToEmployerNotification.objects.filter(
            resume__in=resumes,
            job_posting__id=job_posting_uuid
        ).exists()
        context.update({'resumes': resumes, 'resume_sent': resume_sent})

    context.update({'job_posting': job_posting})
    return render(request, "hh/job_posting.html", context)


@login_required
def like_job_posting(request, job_posting_uuid):
    if request.user.is_employer:
        return JsonResponse({
            "error": "Only job seekers can add to favourites."
        }, status=400)
    else:
        try:
            current_job_posting = JobPosting.objects.get(id=job_posting_uuid)
        except ObjectDoesNotExist:
            return JsonResponse({'error': 'Job posting not found!'}, status=404)
        if request.method == 'PUT':
            data = json.loads(request.body)

            #Checking if the user has the job posting in favourites or not
            if data.get('favourite') is not None:
                try:
                    is_liked_by_user_filter = current_job_posting.liked.get(id=request.user.id)
                    is_liked_by_user = True
                except ObjectDoesNotExist:
                    is_liked_by_user = False

            #Add job posting to favourites or remove it from favourites
                if is_liked_by_user:
                    current_job_posting.liked.remove(request.user)
                    currently_favourite = False
                else:
                    current_job_posting.liked.add(request.user)
                    currently_favourite = True
                current_job_posting.save()
                return JsonResponse({
                    "currently_favourite": currently_favourite,
                })
        # Only PUT request!
        else:
            return JsonResponse({
                "error": "PUT request required."
            }, status=400)


@login_required
def favourite_job_postings(request):
    #Only job seekers can see this page
    if request.user.is_employer:
        raise PermissionDenied()
    favourite_jobs = JobPosting.objects.filter(liked=request.user).order_by('-job_open_date')
    context = {'favourite_jobs': favourite_jobs}
    return render(request, "hh/favourite_job_postings.html", context)


@login_required
def my_job_postings_view(request):
    # Only employers can see this page
    if not request.user.is_employer:
        raise PermissionDenied()
    my_job_postings = JobPosting.objects.filter(employer=request.user).order_by('-job_open_date')

    #Pagination
    pagination_range = 5
    paginator = Paginator(my_job_postings, pagination_range)
    page_number = request.GET.get("page")
    page_object = paginator.get_page(page_number)


    context = {'page_object': page_object}
    return render(request, "hh/my_job_postings.html", context)


@login_required
def search_for_jobs(request):
    #This page is only for job seekers
    if request.user.is_employer:
        raise PermissionDenied()
    context = {'title': 'Search results',
               'countries': JobPosting.COUNTRY_CHOICES,
               'industries': Industry.objects.all(),
               }

    # Search results
    # time to construct the filter
    filter_list = ['search_bar', 'part_time', 'remote', 'country', 'city', 'industry', 'salaryRadio']
    filter_kwargs = get_filter_kwargs(request, filter_list)

    #excluded words if any
    excluded_words_in_query = request.GET.get('exclude_words', "").split()
    excluded_clauses = get_excluded_clauses(excluded_words_in_query)

    if excluded_words_in_query:
        jobs = JobPosting.objects.annotate(
            is_liked=Exists(
                JobPosting.liked.through.objects.filter(
                    jobposting_id=OuterRef('pk'), user=request.user
                )
            )
        ).filter(**filter_kwargs).exclude(
            excluded_clauses
        ).exclude(is_archived=True).order_by("-job_open_date")
    else:
        jobs = JobPosting.objects.annotate(
            is_liked=Exists(
                JobPosting.liked.through.objects.filter(
                    jobposting_id=OuterRef('pk'), user=request.user
                )
            )
        ).filter(**filter_kwargs).exclude(is_archived=True).order_by("-job_open_date")

    # Pagination
    pagination_range = 10
    paginator = Paginator(jobs, pagination_range)
    page_number = request.GET.get("page")
    page_object = paginator.get_page(page_number)

    context.update({'page_object': page_object, 'result_number': jobs.count()})
    return render(request, 'hh/search_for_jobs.html', context)


@login_required
def create_job_posting_view(request):

    # Only an employer account allowed on the page
    if not request.user.is_employer:
        raise PermissionDenied()

    # Creating a new job posting using a form

    form = CreateJobPostingForm(request.POST or None)
    if request.method == 'POST':
        form = CreateJobPostingForm(request.POST, employer=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Job posting successfully created.")
            return redirect('index')
        else:
            for error in list(form.errors.values()):
                messages.error(request, error)
    context = {'form': form}
    return render(request, "hh/create_job_posting.html", context)


@login_required
def edit_profile_view(request):
    if request.user.is_employer:
        profile = request.user.employerprofile
        form = EditEmployerProfileForm(request.POST or None, instance=profile)
    else:
        profile = request.user.jobseekerprofile
        form = EditJobSeekerProfileForm(request.POST or None, instance=profile)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated")
            return redirect('index')
    context = {'profile': profile, 'form': form}
    return render(request, "hh/edit_profile.html", context)


@login_required
def create_resume_view(request):
    #This page is only for job seekers
    if request.user.is_employer:
        raise PermissionDenied()

    form_1 = CreateResumeForm(request.POST or None)
    if request.method == 'POST':
        form_1 = CreateResumeForm(request.POST, user=request.user)
        if form_1.is_valid():
            new_resume = form_1.save()
            return HttpResponseRedirect(reverse("my_resumes"))
    context = {'form_1': form_1}
    return render(request, "hh/create_resume_main.html", context)


@login_required
def edit_resume_main_view(request, resume_uuid):
    if request.user.is_employer:
        raise PermissionDenied()

    resume = get_object_or_404(Resume, id=resume_uuid)
    if resume.user != request.user:
        raise PermissionDenied()

    form = CreateResumeForm(request.POST or None, instance=resume, user=request.user)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, "Resume updated")
            return redirect(resume)
    context = {'form': form, 'resume': resume}
    return render(request, "hh/edit_resume_main.html", context)


@login_required
def edit_resume_education_view(request, resume_uuid):
    if request.user.is_employer:
        raise PermissionDenied()
    try:
        resume = Resume.objects.prefetch_related('education_blocks').get(id=resume_uuid)
    except ObjectDoesNotExist:
        raise Http404()

    # processing post data
    if request.method == 'POST':
        post_dict = generate_post_dict(request)

        for edu_id in post_dict:
            obj, created = ResumeEducationBlock.objects.update_or_create(
                uuid=edu_id,
                resume=resume,
                defaults={
                "educational_institution": post_dict[edu_id]['educational_institution'],
                "specialization": post_dict[edu_id]['specialization'],
                "year_of_graduation": post_dict[edu_id]['year_of_graduation']
                          },
            )
        ResumeEducationBlock.objects.filter(resume=resume).exclude(uuid__in=post_dict).delete()
        messages.success(request, "Resume updated")
        return redirect(resume)
    education_blocks = ResumeEducationBlock.objects.filter(resume=resume).order_by("year_of_graduation")
    context = {'education_blocks': education_blocks, 'resume': resume}
    return render(request, "hh/edit_resume_education.html", context)


@login_required
def edit_resume_work_experience_view(request, resume_uuid):
    if request.user.is_employer:
        raise PermissionDenied()
    try:
        resume = Resume.objects.prefetch_related('education_blocks').get(id=resume_uuid)
    except ObjectDoesNotExist:
        raise Http404()

    #processing post data
    if request.method == 'POST':
        post_dict = generate_post_dict(request)
        print(post_dict)
        for work_id in post_dict:
            date_start = post_dict[work_id]['employment_began']
            date_start = date_start + '-01'
            date_end = post_dict[work_id]['employment_ended'] + '-01' \
                if post_dict[work_id]['employment_ended'] else None
            obj, created = ResumeWorkExperienceBlock.objects.update_or_create(
                uuid=work_id,
                resume=resume,
                defaults={
                    "employer": post_dict[work_id]['organization'],
                    "position": post_dict[work_id]['position'],
                    "job_duties": post_dict[work_id]['job_duties'],
                    "employment_began": date_start,
                    "employment_ended": date_end,
                },
            )
        ResumeWorkExperienceBlock.objects.filter(resume=resume).exclude(uuid__in=post_dict).delete()
        messages.success(request, "Resume updated")
        return redirect(resume)
    work_experience_blocks = ResumeWorkExperienceBlock.objects.filter(resume=resume).order_by("employment_began")
    context = {'work_experience_blocks': work_experience_blocks, 'resume': resume}
    return render(request, "hh/edit_resume_work_experience.html", context)


@login_required
def my_resumes_view(request):
    if request.user.is_employer:
        raise PermissionDenied()
    my_resumes = Resume.objects.filter(user=request.user)
    context = {'my_resumes': my_resumes}
    return render(request, "hh/my_resumes.html", context)


@login_required
def send_resume(request, job_posting_uuid, resume_uuid):
    ResumeToEmployerNotification.objects.get_or_create(
        resume=get_object_or_404(Resume, id=resume_uuid),
        job_posting=get_object_or_404(JobPosting, id=job_posting_uuid),
        )
    job_posting = JobPosting.objects.get(id=job_posting_uuid)
    return redirect(job_posting)


@login_required
def archive_job_posting(request, job_posting_uuid):
    try:
        job_posting = JobPosting.objects.get(id=job_posting_uuid)
        job_posting.is_archived = True
        job_posting.save()
    except ObjectDoesNotExist:
        raise Http404
    print("function worked")
    return redirect(job_posting)


@login_required
def delete_resume(request, resume_uuid):
    Resume.objects.get(id=resume_uuid).delete()
    return HttpResponseRedirect(reverse("my_resumes"))


@login_required
def resume_view(request, resume_uuid):
    context = {}
    if request.user.is_employer:
        raise PermissionDenied()

    try:
        resume = Resume.objects.get(id=resume_uuid)
    except ObjectDoesNotExist:
        raise Http404()
    education_blocks = ResumeEducationBlock.objects.filter(resume=resume).order_by('-year_of_graduation')
    work_experience_blocks = ResumeWorkExperienceBlock.objects.filter(resume=resume).order_by('-employment_ended')
    age = calculate_age(resume.date_of_birth)
    context.update({'resume': resume,
                    'age': age,
                    'education_blocks': education_blocks,
                    'work_experience_blocks': work_experience_blocks})
    return render(request, "hh/resume.html", context)


def my_notifications_view(request):
    if not request.user.is_employer:
        raise PermissionDenied()
    context = {}

    notifications = ResumeToEmployerNotification.objects.filter(
                job_posting__in=JobPosting.objects.filter(employer=request.user)
                ).select_related("job_posting").order_by("-date")

    # pagination
    pagination_range = 15
    paginator = Paginator(notifications, pagination_range)
    page_number = request.GET.get("page")
    page_object = paginator.get_page(page_number)
    context.update({"page_object": page_object})

    return render(request, "hh/my_notifications.html", context)


def login_view(request):
    if request.method == "POST":

        # Attempt to sign user in
        username = request.POST["username"]
        password = request.POST["password"]
        user = authenticate(request, username=username, password=password)

        # Check if successful authentication
        if user is not None:
            login(request, user)
            return HttpResponseRedirect(reverse("index"))
        else:
            return render(request, "hh/login.html", {
                "message": "Invalid username and/or password."
            })
    else:
        return render(request, "hh/login.html")


def logout_view(request):
    logout(request)
    return HttpResponseRedirect(reverse("index"))


def register_view(request):
    if request.method == 'POST':

        username = request.POST["username"]
        email = request.POST["email"]
        first_name = request.POST['first_name']
        last_name = request.POST['last_name']
        password = request.POST["password"]
        confirmation = request.POST["confirmation"]
        if password != confirmation:
            messages.error(request, "Passwords don't match")
            return render(request, "hh/register.html")
        is_employer = True if request.POST["user_type"] == 'employer' else False

        # Creating the new user
        try:
            user = User.objects.create_user(username, email, password,
                                            is_employer=is_employer, first_name=first_name, last_name=last_name)
        except IntegrityError:
            messages.error(request, "Username already taken")
            return render(request, "hh/register.html")

        # EmployerProfile or JobSeekerProfile
        # are created by create_user_profile function which is a signal receiver located in models.py

        # Modifying additional profile
        if user.is_employer:
            EmployerProfile.objects.filter(user=user).update(
                company_name=request.POST.get('company_name', None),
                company_logo=request.POST.get('company_logo', None),
                telegram_ID=request.POST.get('telegram_ID', None),
                phone_number=request.POST.get('phone_number', None),
            )
        else:
            JobSeekerProfile.objects.filter(user=user).update(
                image=request.POST.get('photo', None),
                telegram_ID=request.POST.get('telegram_ID', None),
                phone_number=request.POST.get('phone_number', None),
                preferred_country=request.POST.get('country', None),
                preferred_location=request.POST.get('city', None),
            )
        login(request, user)
        messages.success(request, "Welcome!")
        return HttpResponseRedirect(reverse("index"))
    return render(request, "hh/register.html")
