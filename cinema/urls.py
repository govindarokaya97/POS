from django.urls import path

from . import views


urlpatterns = [

    path("", views.cinema_dashboard, name="cinema_dashboard"),

    # Sell tickets: seats -> bill/payment -> print
    path("show/<int:id>/seats/", views.seat_selection, name="seat_selection"),
    path("show/<int:id>/checkout/", views.ticket_checkout, name="ticket_checkout"),
    path("booking/<int:id>/", views.ticket_print, name="ticket_print"),

    # Back office at the counter
    path("bookings/", views.booking_list, name="booking_list"),
    path("booking/<int:id>/cancel/", views.booking_cancel, name="booking_cancel"),
    path("verify/", views.verify_ticket, name="verify_ticket"),
    path("report/", views.cinema_report, name="cinema_report"),

]
