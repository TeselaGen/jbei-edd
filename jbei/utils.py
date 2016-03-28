"""
A catch-all module for general utility code that doesn't clearly belong elsewhere.
"""
import arrow


class UserInputTimer(object):
    """
    A simple wrapper over tha raw_input() builtin that handles tracking the amount of time spent
    waiting on user input.
    """
    def __init__(self):
        now = arrow.utcnow()
        self._waiting_on_user_delta = now - now

    def user_input(self, prompt=None):
        """
        A wrapper function for getting user input while keeping track of the amount of time spent
        waiting for it.
        """
        start = arrow.utcnow()
        try:
            return raw_input(prompt)
        finally:
            end = arrow.utcnow()
            self._waiting_on_user_delta += end - start

    @property
    def wait_time(self):
        return self._waiting_on_user_delta

_SECONDS_PER_HOUR = 3600
_HOURS_PER_DAY = 24
_SECONDS_PER_MINUTE = 60
_SECONDS_PER_MONTH = _SECONDS_PER_HOUR * _HOURS_PER_DAY * 30
_SECONDS_PER_YEAR = _SECONDS_PER_MONTH * 12   # NOTE: this causes years to have 360 days, but it's
                                            # consistent / good enough
_SECONDS_PER_DAY = _SECONDS_PER_HOUR * _HOURS_PER_DAY


def to_human_relevant_delta(seconds):
    """
    Converts the input to a human-readable time duration, with only applicable units displayed,
    and with precision limited to a level where humans are likely to take interest based on the
    largest time increment present in the input. NOTE: if the arrow library (e.g. humanize(
    )) fulfills your needs, you should probably use that. It doesn't seem
    to support good phrasing for simple time quantities that aren't relative to a specific
    timestamp, or to give sufficiently granular output to help with software performance analysis.

    Daylight savings time, leap years, etc are not
    taken into account, months are assumed to have 30 days, and years have 12 months (=360 days).
    The minimum time increment displayed for any value is milliseconds. The output of this method is
    intended exclusively for human use, e.g. for displaying task execution time in the GUI and/or
    logs. If you care about precise formatting of the output, this probably isn't the method for
    you.

    Note that the result is designed to be most useful at lower time increments, and probably needs
    additional formatting (e.g. more liberal and/or configurable use of abbreviations and max.
    precision) for use at longer time intervals. As the output is intended for human use, no
    guarantee is made that the output will be constant over time, though changes can be
    reasonably expected to make the output more relevant and/or readable.



    NOTE: a Java port of this method also exists in edd-analytics-java. Consider maintaining that
    implementation and its unit tests along with this one.

    :param seconds: time in seconds
    :return:
    """
    # TODO: as a future improvement, consider adding an optional minimum precision parameter
    # to improve flexibility for more use cases

    def _pluralize(str, quantity):
        if quantity > 1:
            return str + 's'
        return str

    def _append(formatted_duration, part_str):
        if formatted_duration:
            return ' '.join([formatted_duration, part_str])
        else:
            return part_str

    formatted_duration = ''

    # compute years
    if seconds >= _SECONDS_PER_YEAR:
        years = seconds // _SECONDS_PER_YEAR
        seconds %= _SECONDS_PER_YEAR
        years_str = '%d year' % years
        formatted_duration = _append(formatted_duration, years_str)
        formatted_duration = _pluralize(formatted_duration, years)

    # compute months
    if seconds >= _SECONDS_PER_MONTH:
        months = seconds // _SECONDS_PER_MONTH
        seconds %= _SECONDS_PER_MONTH

        months_str = '%d month' % months
        formatted_duration = _append(formatted_duration, months_str)
        formatted_duration = _pluralize(formatted_duration, months)

    # compute days
    if seconds >= _SECONDS_PER_DAY:
        days = seconds // _SECONDS_PER_DAY
        seconds %= _SECONDS_PER_DAY
        days_str = '%d day' % days
        formatted_duration = _append(formatted_duration, days_str)
        formatted_duration = _pluralize(formatted_duration, days)

    # compute hours
    if seconds >= _SECONDS_PER_HOUR:
        hours = seconds // _SECONDS_PER_HOUR
        seconds %= _SECONDS_PER_HOUR
        hours_str = '%d hour' % hours
        formatted_duration = _append(formatted_duration, hours_str)
        formatted_duration = _pluralize(formatted_duration, hours)

    # store results so far so we can detect later whether the time has any increment greater
    # than minutes
    larger_than_minutes = formatted_duration
    minutes = 0

    # compute minutes
    if seconds >= _SECONDS_PER_MINUTE:
        minutes = seconds // _SECONDS_PER_MINUTE
        seconds %= _SECONDS_PER_MINUTE
        minutes_str = '%d minute' % minutes
        formatted_duration = _append(formatted_duration, minutes_str)
        formatted_duration = _pluralize(formatted_duration, minutes)

    # don't compute fractional seconds if humans are unlikely to care
    show_fractional_seconds = (not larger_than_minutes) and (minutes < 10)

    if (seconds > 0) or (not formatted_duration):
        # show ms if no greater time increment exists in the data
        if (seconds < 1) and not formatted_duration:
            formatted_duration = '%d ms' % round(seconds * 1000)
        # otherwise, append either fractional or rounded seconds
        elif show_fractional_seconds:
            decimal_sec_str = '%.2f s' % seconds
            formatted_duration = _append(formatted_duration, decimal_sec_str)
        else:
            int_sec_str = '%d s' % round(seconds)
            formatted_duration = _append(formatted_duration, int_sec_str)

    return formatted_duration