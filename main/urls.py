from django.conf.urls import patterns, url
from django.contrib.auth.decorators import login_required
from main import views


urlpatterns = patterns('',
    url(r'^$', login_required(views.IndexView.as_view()), name='index'),
    url(r'^study/(?P<pk>\d+)/$', login_required(views.StudyDetailView.as_view()), name='detail'),
    url(r'^study/search/$', login_required(views.study_search)),
)