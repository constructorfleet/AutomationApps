import asyncio
import datetime
import re
import logging
import imghdr
from email.headerregistry import Address
from email.message import EmailMessage
from string import Formatter

from aiosmtplib import SMTP

_LOGGER = logging.getLogger(__name__)

REPLACER_FUNCTION_TEMPLATE = re.compile(r"^{([^}]*)}$")
REPLACER_FUNCTION_SPEC = re.compile(r"(([a-z.]*)\((.*)?)\)")

SECOND_CONVERSION = {
        'seconds': 1,
        'minutes': 60,
        'hours': 3600
        }


def minutes_to_seconds(minutes):
    return minutes * 60


def converge_types(v1, v2):
    if v1 is None:
        if v2 is None:
            return None, None
        else:
            return None, v2
    if v2 is None:
        if v1 is None:
            return None, None
        else:
            return v1, v2

    v1_type = type(v1)
    v2_type = type(v2)
    if v1_type == v2_type:
        return v1, v2

    if v1_type in [int, float] and v1_type in [int, float]:
        return float(v1), float(v2)
    elif v1_type == bool or v2_type == bool:
        return bool(v1), bool(v2)

    try:
        return float(v1), float(v2)
    except Exception as err:
        _LOGGER.warning('Not floats')

    try:
        return v1, type(v1)(v2)
    except Exception as err:
        _LOGGER.warning('Cannot convert {} to  type of {} ({})'.format(v2, v1, type(v1)))

    try:
        return type(v2)(v1), v2
    except Exception as err:
        _LOGGER.warning('Cannot convert {} to  type of {} ({})'.format(v1, v2, type(v2)))

    # Tried everything, return originals
    return v1, v2


def json_serializer(obj):
    if isinstance(obj, datetime.datetime):
        return obj.isoformat
    return str(obj)


async def send_email(
        subject,
        content,
        to,
        username,
        password,
        display_name=None,
        cc_recipients=None,
        bcc_recipients=None,
        important=False,
        attach_img=None,
        content_type='text/plain',
        server='smtp.gmail.com',
        port=465):

    if not to or not username or not password or not subject or not content:
        return False

    def email_name(addr):
        return addr.split('@')[0]

    def email_domain(addr):
        return addr.split('@')[1]

    def generate_header(addresses):
        if isinstance(addresses, Address):
            return str(addresses)
        return ', '.join([str(addr) for addr in addresses])

    display_name = display_name or email_name(username)

    from_addr = Address(display_name, display_name.lower(), email_domain(username))
    to_addr = [
        Address(
            email_name(recipient),
            email_name(recipient).lower(),
            email_domain(recipient)
        )
        for recipient
        in (to if isinstance(to, list) else [to])
    ]
    cc_addr = [
        Address(
            email_name(recipient),
            email_name(recipient).lower(),
            email_domain(recipient)
        )
        for recipient
        in (cc_recipients or [])
    ]
    bcc_addr = [
        Address(
            email_name(recipient),
            email_name(recipient).lower(),
            email_domain(recipient)
        )
        for recipient
        in (bcc_recipients or [])
    ]

    # Build the list of recipients (To + Bcc):
    recipients = [addr.addr_spec for addr in (to_addr + cc_addr + bcc_addr)]

    # Build the EmailMessage object:
    message = EmailMessage()
    message.add_header("From", generate_header(from_addr))
    message.add_header("To", generate_header(to_addr))
    if cc_addr:
        message.add_header("Cc", generate_header(cc_addr))
    if bcc_addr:
        message.add_header("Bcc", generate_header(bcc_addr))
    message.add_header("Subject", subject)
    message.add_header("Content-type", content_type, charset="utf-8")
    if attach_img:
        message.add_attachment(
            attach_img,
            main_type='image',
            subtype=imghdr.what(None, attach_img)
        )
    if important:
        message.add_header("X-Priority", "1 (Highest)")
        message.add_header("X-Priority", "1 (Highest)")
        message.add_header("X-MSMail-Priority", "High")
        message.add_header("Importance", "High")

    message.set_content(content)

    async with SMTP(hostname=server, port=port, use_tls=True, username=username, password=password) as client:
        await client.sendmail(from_addr.addr_spec, recipients, message.as_string())

    return True


class KWArgFormatter(Formatter):
    def __init__(self, get_state=None):
        self.get_state = get_state

    def format(self, format_string, /, *args, **kwargs):
        if self.get_state:
            kwargs = {k: self._process_template(v) for k, v in kwargs.items()}
        return super().format(format_string, *args, **kwargs)

    def _process_template(self, method, value):
        sub_function = REPLACER_FUNCTION_SPEC.match(value)
        if not sub_function:
            return value
        value = self._process_template(*list(sub_function.groups())[1:])
        if method == 'state':
            return asyncio.get_event_loop().run_until_complete(self.get_state(value, attribute='all'))
        if method.startswith('duration'):
            unit = 'seconds' if len(method.split('.')) < 2 else method.split('.')[1]
            now = then = datetime.datetime.utcnow().timestamp()
            if 'last_changed' in value:
                then = datetime.datetime.fromisoformat(value['last_changed']).timestamp()
            return datetime.timedelta(now - then).seconds/SECOND_CONVERSION.get(unit, 1)

    def get_value(self, key, args, kwds):
        if isinstance(key, str):
            try:
                return kwds[key]
            except KeyError:
                return key
        else:
            return super(KWArgFormatter, self).get_value(key, args, kwds)