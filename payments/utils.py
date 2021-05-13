from datetime import date

from django.utils.translation import gettext_lazy as _


def get_month_choices():
    month_choices = [(str(x), "%02d" % (x,)) for x in range(1, 13)]
    return [("", _("Month"))] + month_choices


def get_year_choices():
    year_choices = [
        (str(x), str(x)) for x in range(date.today().year, date.today().year + 15)
    ]
    return [("", _("Year"))] + year_choices
