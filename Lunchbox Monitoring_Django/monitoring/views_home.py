from django.shortcuts import render
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.db.models import Count, Avg, Max, Min

class HomeView(TemplateView):
    """View for the home page."""
    template_name = 'home.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add any additional context data here
        return context


class DashboardTemplateView(LoginRequiredMixin, TemplateView):
    """View for the dashboard page."""
    template_name = 'dashboard.html'
    login_url = '/admin/login/'
    redirect_field_name = 'next'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Add any additional context data for the dashboard
        context.update({
            'page_title': 'Dashboard',
            'current_time': timezone.now(),
            # Add more context data as needed
        })
        
        return context
