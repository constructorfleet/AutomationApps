from datetime import datetime

import requests
import voluptuous as vol

from common.base_app import BaseApp
from common.utils import KWArgFormatter

ARG_API_KEY = 'api_key'
ARG_COUNTRY = 'country'

DEFAULT_COUNTRY = 'US'

BASE_URL = \
    'https://calendarific.com/api/v2/holidays?api_key={api_key}&country={country}&year={year}'

KEY_YEAR = 'year'

VALENTINES = "Valentine's Day"
ST_PATRICKS = "St. Patrick's Day"
EASTER = 'Easter Sunday'
CINCO_DE_MAYO = 'Cinco de Mayo'
MOTHERS_DAY = "Mother's Day'"
MEMORIAL_DAY = 'Memorial Day'
FATHERS_DAY = "Father's Day"
INDEPENDENCE_DAY = 'Independence Day'
LABOR_DAY = 'Labor Day'
HALLOWEEN = 'Halloween'
THANKSGIVING = 'Thanksgiving Day'
CHANUKAH = 'Last Day of Chanuka'
CHRISTMAS = 'Christmas Day'
NEW_YEARS_EVE = "New Year's Eve"

HOLIDAY_COLORS = {
    VALENTINES: [
        (94, 8, 30),
        (181, 26, 58),
        (226, 71, 103),
        (228, 131, 151)
    ],
    ST_PATRICKS: [
        (34, 77, 23),
        (9, 148, 65),
        (159, 218, 64),
        (217, 223, 29)
    ],
    EASTER: [
        (255, 247, 0),
        (0, 255, 127),
        (181, 115, 220),
        (238, 130, 238)
    ],
    CINCO_DE_MAYO: [
        (40, 195, 168),
        (238, 225, 95),
        (238, 0, 0),
        (176, 17, 145)
    ],
    MOTHERS_DAY: [
        (241, 68, 114),
        (241, 125, 182),
        (254, 212, 12),
        (133, 175, 75)
    ],
    MEMORIAL_DAY: [
        (18, 18, 125),
        (3, 234, 247),
        (219, 215, 215),
        (178, 0, 0)
    ],
    FATHERS_DAY: [
        (101, 209, 237),
        (254, 243, 128),
        (250, 122, 88),
        (194, 94, 68)
    ],
    INDEPENDENCE_DAY: [
        (255, 0, 0),
        (255, 255, 255),
        (0, 0, 255),
        (255, 255, 255)
    ],
    LABOR_DAY: [
        (18, 18, 125),
        (3, 234, 247),
        (219, 215, 215),
        (178, 0, 0)
    ],
    HALLOWEEN: [
        (252, 70, 5),
        (234, 12, 12),
        (148, 1, 148),
        (63, 171, 67)
    ],
    THANKSGIVING: [
        (193, 49, 28),
        (235, 186, 56),
        (98, 48, 4),
        (189, 184, 80)
    ],
    CHANUKAH: [
        (242, 235, 219),
        (154, 184, 194),
        (58, 86, 160),
        (218, 174, 75)
    ],
    CHRISTMAS: [
        (179, 0, 12),
        (220, 61, 42),
        (0, 179, 44),
        (12, 89, 1)
    ],
    NEW_YEARS_EVE: [
        (212, 175, 55),
        (192, 192, 192),
        (0, 0, 255),
        (255, 255, 255)
    ],
}


class HolidayColors(BaseApp):
    config_schema = vol.Schema({
        vol.Required(ARG_API_KEY): str,
        vol.Optional(ARG_COUNTRY, default=DEFAULT_COUNTRY):
            vol.All(vol.Length(min=2, max=2), vol.Upper)
    }, extra=vol.ALLOW_EXTRA)

    _for_year = None
    _holidays = {}

    def initialize_app(self):
        self.debug('File %s' % self._persistent_data_file)
        self.debug('Data {}'.format(str(self.data)))
        if self._for_year != datetime.now().year:
            self.debug('Retrieving holidays')
            self._retrieve_holidays()

        self.debug(str(self._holidays))

    @property
    def api_url(self):
        return KWArgFormatter().format(
            BASE_URL,
            api_key=self.config[ARG_API_KEY],
            country=self.config[ARG_COUNTRY],
            year=str(datetime.now().year)
        )

    def get_closest_holiday_colors(self):
        now = datetime.now()
        if self._for_year != now.year:
            self.info('New year, reload data...')
            self._retrieve_holidays()

        closest = min(
            self._holidays.values(),
            key=lambda x: abs(x - now))
        holiday = [name for name, date in self._holidays.items() if
                   closest.month == date.month and closest.day == date.day][0]
        self.debug('Holiday %s', holiday)
        return HOLIDAY_COLORS.get(holiday, [(255, 255, 255)])

    def _retrieve_holidays(self):
        self.clear_data()
        response = requests.get(self.api_url)
        try:
            response.raise_for_status()
            json = response.json()
            holidays = json.get('response', {}).get('holidays', [])
            if not holidays:
                self.error('Unable to parse holidays from response')
                return
            self._for_year = datetime.now().year
            self.record_data(KEY_YEAR, self._for_year)

            for holiday in holidays:
                name = holiday.get('name', '')
                self.debug('Got holiday %s', name)
                if name not in HOLIDAY_COLORS.keys():
                    self.debug('%s not in colors', name)
                    continue
                holiday_date = holiday.get('date', {}).get('datetime', {})
                self.record_data(name, holiday_date)
                self._holidays[name] = self._parse_holiday_date(holiday_date)

        except requests.HTTPError as err:
            self.error(str(err))

    def _on_persistent_data_loaded(self):
        self.debug('Transforming json data')

        self._for_year = self.data[KEY_YEAR]

        self.debug('FOR YEAR {}'.format(self._for_year))

        for name, holiday_date in self.data.items():
            if name == KEY_YEAR and name not in HOLIDAY_COLORS.keys():
                continue

            self._holidays[name] = self._parse_holiday_date(holiday_date)

        self.debug("Holidays %%s", str(self._holidays))

    def _parse_holiday_date(self, holiday_date):
        day = holiday_date.get('day')
        month = holiday_date.get('month')
        year = holiday_date.get('year')
        if day and month and year:
            return datetime(
                day=day,
                month=month,
                year=year
            )
        else:
            self.warning('Missing a date piece %s', str(holiday_date))
            return None
