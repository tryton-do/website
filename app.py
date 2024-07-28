#!/usr/bin/env python3
import ast
import datetime
import enum
import functools
import glob
import hashlib
import logging
import operator
import os
import re
import unicodedata
from collections import OrderedDict, namedtuple
from functools import partial
from http import HTTPStatus
from logging.handlers import SMTPHandler
from operator import attrgetter
from random import choice, sample, shuffle
from urllib.parse import quote, urljoin, urlparse

import requests
from colorthief import ColorThief
from flask import (
    Flask, abort, make_response, redirect, render_template, request, url_for)
from flask_babel import Babel, _
from flask.logging import default_handler
from flask_caching import Cache
from flask_cdn import CDN
from flask_cdn import url_for as _cdn_url_for
from flask_gravatar import Gravatar
from flask_sitemap import Sitemap
from icalendar import Calendar, Event
from jinja2 import TemplateNotFound
from lxml import html, objectify
from werkzeug.middleware.proxy_fix import ProxyFix

NEWS_URL = 'https://discuss.tryton.org/c/news'
NEWS_RSS_URL = NEWS_URL + '.rss'
CALENDAR_URL = 'https://discuss.tryton.org/upcoming-events'
CALENDAR_JSON = 'https://discuss.tryton.org/discourse-post-event/events.json'
SUPPORTERS_URL = (
    'https://foundation.tryton.org:9000/foundation/foundation/1/supporters')
DONATORS_URL = (
    'https://foundation.tryton.org:9000/foundation/foundation/1/donators'
    '?account=732&account=734&duration=730')
DONATIONS_URL = (
    'https://foundation.tryton.org:9000/foundation/foundation/1/donations'
    '?account=732&account=734')

CRITICAL_CSS_DIR = os.environ.get('CRITICAL_CSS')
CRITICAL_CSS_COOKIE = 'critical-css'

cache = Cache(config={
        'CACHE_TYPE': (
            'null' if ast.literal_eval(os.environ.get('DEBUG', 'True'))
            else 'simple')})
if os.environ.get('MEMCACHED'):
    cache.config['CACHE_TYPE'] = 'memcached'
    cache.config['CACHE_MEMCACHED_SERVERS'] = (
        os.environ['MEMCACHED'].split(','))
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = datetime.timedelta(days=365)
app.config['CACHE_DEFAULT_TIMEOUT'] = 60 * 60
app.config['PREFERRED_URL_SCHEME'] = 'https'
app.config['SERVER_NAME'] = os.environ.get('SERVER_NAME')
app.config['SITEMAP_INCLUDE_RULES_WITHOUT_PARAMS'] = True
app.config['SITEMAP_VIEW_DECORATORS'] = [cache.cached()]
app.config['BABEL_DEFAULT_LOCALE'] = 'es'
app.config['BABEL_SUPPORTED_LOCALES'] = ['en', 'es']
app.config['SITEMAP_IGNORE_ENDPOINTS'] = {
    'contribute-alt',
    'donate-alt',
    'donate_cancel',
    'donate_thanks',
    'download-alt',
    'event-alt',
    'events',
    'events-alt',
    'events-ics',
    'favicon',
    'flask_sitemap.page',
    'flask_sitemap.sitemap',
    'foundation-alt',
    'news-alt',
    'news_rss',
    'presentations-alt',
    'robots',
    'service_providers-alt',
    'success_stories-alt',
    'supporters-alt',
    'warmup',
    }
app.config['SITEMAP_URL_SCHEME'] = 'https'
app.config['DOWNLOADS_DOMAIN'] = os.environ.get(
    'DOWNLOADS_DOMAIN', 'downloads.tryton.org')
app.config['VIDEOS_DOMAIN'] = os.environ.get(
    'VIDEOS_DOMAIN', 'videos.tryton.org')
app.config['CDN_DOMAIN'] = os.environ.get('CDN_DOMAIN')
app.config['CDN_HTTPS'] = ast.literal_eval(os.environ.get('CDN_HTTPS', 'True'))
app.config['GRAVATAR_SIZE'] = 198
app.config['GRAVATAR_DEFAULT'] = 'mp'
app.config['GRAVATAR_USE_SSL'] = True
if app.config['CDN_DOMAIN']:
    app.config['GRAVATAR_BASE_URL'] = '%s://%s/' % (
        'https' if app.config['CDN_HTTPS'] else 'http',
        app.config['CDN_DOMAIN'])
else:
    app.config['GRAVATAR_BASE_URL'] = '/'
app.jinja_env.lstrip_blocks = True
app.jinja_env.trim_blocks = True
app.jinja_env.autoescape = (
    lambda filename: (
        app.select_jinja_autoescape(filename)
        or filename.endswith('.html.jinja')))
cache.init_app(app)
CDN(app)
gravatar = Gravatar(app)
sitemap = Sitemap(app=app)

babel = Babel(app)

@babel.localeselector
def get_locale():
    lang = request.args.get('lang')
    if lang:
        return lang
    return request.accept_languages.best_match(app.config['BABEL_SUPPORTED_LOCALES'])

@app.before_request
def before_request():
    g.lang = get_locale()
    
def url_for_self(**args):
    return url_for(request.endpoint, **dict(request.args, **args))

@app.context_processor
def inject_self():
    return dict(url_for_self=url_for_self)

def json_default(o):
    if hasattr(o, '__json__'):
        return o.__json__()
    raise TypeError(f'Object of type {o.__class__.__name__} '
        f'is not JSON serializable')


app.jinja_env.policies['json.dumps_kwargs'] = {
    'sort_keys': True,
    'default': json_default,
    }


_slugify_strip_re = re.compile(r'[^\w\s-]')
_slugify_hyphenate_re = re.compile(r'[-\s]+')


@app.template_filter('slugify')
def slugify(value):
    if not isinstance(value, str):
        value = str(value)
    value = unicodedata.normalize('NFKD', value)
    value = str(_slugify_strip_re.sub('', value).strip())
    return _slugify_hyphenate_re.sub('-', value)


def url_for_downloads(*args):
    return urljoin(
        '//' + app.config['DOWNLOADS_DOMAIN'], os.path.join(*map(quote, args)))


@app.context_processor
def inject_url_for_dowloads():
    return dict(url_for_downloads=url_for_downloads)


def url_for_videos(*args):
    return urljoin(
        '//' + app.config['VIDEOS_DOMAIN'], os.path.join(*map(quote, args)))


@app.context_processor
def inject_url_for_videos():
    return dict(url_for_videos=url_for_videos)


def cdn_url_for(*args, **kwargs):
    if app.config['CDN_DOMAIN']:
        return _cdn_url_for(*args, **kwargs)
    else:
        return url_for(*args, **kwargs)


def cache_key_prefix_view():
    scheme = 'https' if request.is_secure else 'http'
    if not request.cookies.get(CRITICAL_CSS_COOKIE):
        return 'view/%s/%s/%s' % (
            scheme, request.path, critical_css(timestamp=True))
    else:
        return 'view/%s/%s' % (scheme, request.path)


LinkHeader = namedtuple(
    'LinkHeader', ['endpoint', 'values', 'params'])

PRECONNECT_HEADERS = [
    LinkHeader('index', {}, {'rel': 'preconnect'}),
    ]
JS_LINK_HEADERS = [
    LinkHeader('static', {'filename': 'js/main.js'}, {
            'rel': 'preload', 'as': 'script', 'nopush': True}),
    ]
CSS_LINK_HEADERS = [
    LinkHeader(
        'static', {'filename': 'css/main.css'}, {
            'rel': 'preload', 'as': 'style', 'nopush': True}),
    LinkHeader(
        'static', {'filename': 'fonts/Roboto.woff2'}, {
            'rel': 'preload', 'as': 'font', 'nopush': True,
            'crossorigin': True}),
    LinkHeader(
        'static', {'filename': 'fonts/material-icons.woff2'}, {
            'rel': 'preload', 'as': 'font', 'nopush': True,
            'crossorigin': True}),
    ]


def add_links(links):
    def format_param(param):
        key, value = param
        if value is True:
            return key
        else:
            return '%s=%s' % (key, value)

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            response = make_response(func(*args, **kwargs))
            for link in links:
                if (link.endpoint == 'index'
                        or (link.endpoint == 'static'
                            and link.values.get(
                                'filename', '').startswith('fonts/'))):
                    if (app.config['CDN_DOMAIN']
                            and not app.config['CDN_DEBUG']):
                        urls = app.url_map.bind(
                            app.config['CDN_DOMAIN'], url_scheme='https')
                        url = urls.build(
                            link.endpoint, link.values, force_external=True)
                    else:
                        url = url_for(link.endpoint, **link.values)
                else:
                    url = cdn_url_for(link.endpoint, **link.values)
                params = '; '.join(map(format_param, link.params.items()))
                value = '<{url}>; {params}'.format(
                    url=url,
                    params=params)
                response.headers.add('Link', value)
            return response
        return wrapper
    return decorator


@app.after_request
def add_cache_control_header(response):
    if 'Cache-Control' not in response.headers:
        response.cache_control.max_age = app.config['CACHE_DEFAULT_TIMEOUT']
        response.cache_control.public = True
    return response


def url_for_canonical(endpoint=None, **values):
    if endpoint is None:
        endpoint = request.endpoint
    if not endpoint:
        return ''
    scheme = 'https' if not app.debug else None
    return url_for(endpoint, _external=True, _scheme=scheme, **values)


@app.context_processor
def inject_canonical():
    return dict(url_for_canonical=url_for_canonical)


def critical_css(timestamp=False):
    if (CRITICAL_CSS_DIR
            and request.endpoint
            and not request.cookies.get(CRITICAL_CSS_COOKIE)):
        file = os.path.join(CRITICAL_CSS_DIR, request.endpoint + '.css')
        if os.path.exists(file):
            if timestamp:
                return int(os.path.getmtime(file))
            else:
                return open(file, 'r').read()


@app.after_request
def add_critical_css_cookie(response):
    if (CRITICAL_CSS_DIR
            and response.mimetype == 'text/html'
            and not request.cookies.get(CRITICAL_CSS_COOKIE)):
        response.set_cookie(CRITICAL_CSS_COOKIE, '1')
    return response


@app.context_processor
def inject_critical_css():
    return dict(critical_css=critical_css)


@cache.memoize(timeout=365 * 24 * 60 * 60)
def dominant_color(path):
    if app.debug:
        return '#000'
    try:
        color = ColorThief(
            os.path.join(app.static_folder, path)).get_color(quality=1)
    except Exception:
        return '#000'
    return '#%02x%02x%02x' % color


@app.context_processor
def inject_dominant_color():
    return dict(dominant_color=dominant_color)


HEART = ('<span '
    'class="material-icons beat" aria-hidden="true" '
    'style="color:#d9534f; font-size: inherit; vertical-align: middle">'
    'favorite'
    '</span>')


@app.route('/')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def index():
    return render_template(
        'index.html.jinja',
        news=list(news_items(3)),
        next_events=next_events(3))


@app.context_processor
def inject_menu():
    menu = OrderedDict()
    menu['Tryton'] = [
        ('Success Stories', url_for('success_stories')),
        ('News', url_for('news')),
        ('Try it', url_for('demo')),
        ('Get Tryton', url_for('download')),
        ('Documentation', '//docs.tryton.org/'),
        ('Code', '//code.tryton.org/'),
        ]
    menu['Community'] = [
        ('Forum', url_for('forum')),
        ('Presentations', url_for('presentations')),
        ('Get Help', 'https://discuss.tryton.org/c/support'),
        ('Contribute', url_for('contribute')),
        ('How to Develop', url_for('develop')),
        ]
    menu['Foundation'] = [
        ('About', url_for('foundation')),
        ('Supporters', url_for('supporters')),
        (HEART + ' Donations', url_for('donate')),
        ]
    menu['Services'] = [
        ('Service Providers', url_for('service_providers')),
        ('Become a Service Provider', url_for('service_providers_start')),
        ]
    return dict(menu=menu, datetime=datetime)


@app.context_processor
def inject_copyright_dates():
    return dict(copyright_dates='2008-%s' % datetime.date.today().year)


@app.context_processor
def inject_heart():
    return dict(heart=HEART)


@app.route('/robots.txt')
@cache.cached()
def robots():
    response = make_response(render_template('robots.txt.jinja'))
    response.mimetype = 'text/plain'
    return response


@app.route('/news')
@app.route('/news/index.html', endpoint='news-alt')
def news():
    return redirect(NEWS_URL)


@app.route('/news.rss')
@app.route('/rss.xml')
def news_rss():
    return redirect(NEWS_RSS_URL)


@cache.memoize(timeout=60 * 60)
def fetch_news_items():
    return requests.get(NEWS_RSS_URL).content


def news_items(size=-1):
    try:
        root = objectify.fromstring(fetch_news_items())
    except Exception:
        app.logger.error('fail to fetch news', exc_info=True)
        return
    for item in root.xpath('/rss/channel/item')[:size]:
        yield item


@app.template_filter('news_text')
def news_text(content):
    block = html.fromstring(str(content))
    for box in block.find_class('lightbox-wrapper'):
        box.drop_tree()
    return block.text_content().strip()


@app.route('/events')
@app.route('/events.html', endpoint='events-alt')
def events():
    return redirect(CALENDAR_URL)


@app.route('/events.ics', endpoint='events-ics')
def events_ics():
    response = make_response(fetch_events())
    response.mimetype = 'text/calendar'
    return response


@cache.memoize(timeout=60 * 60 * 24)
def fetch_events():
    def parse_dt(value):
        return datetime.datetime.fromisoformat(value.rstrip('Z'))
    data = requests.get(CALENDAR_JSON).json()
    calendar = Calendar()
    for data in requests.get(CALENDAR_JSON).json()['events']:
        event = Event()
        if data.get('starts_at'):
            event.add('dtstart', parse_dt(data['starts_at']))
        if data.get('ends_at'):
            event.add('dtend', parse_dt(data['ends_at']))
        event['summary'] = data['name']
        event['url'] = urljoin(CALENDAR_JSON, data['post']['url'])
        calendar.add_component(event)
    return calendar.to_ical()


def next_events(size=-1):
    today = datetime.date.today()
    try:
        cal = Calendar.from_ical(fetch_events())
    except Exception:
        app.logger.error('fail to fetch events', exc_info=True)
        return []

    events = []
    for event in cal.walk('vevent'):
        end_date = (event.get('dtend') or event.get('dtstart')).dt
        if date(end_date) >= today:
            events.append(event)

    def start_date(event):
        return date(event.get('dtstart').dt)

    return sorted(events, key=start_date)[:size]


@app.template_filter('date')
def date(datetime):
    if hasattr(datetime, 'date'):
        return datetime.date()
    return datetime


class Case:
    def __init__(self, title, description, taglines=None, story=False):
        self.title = title
        self.description = description
        self.taglines = taglines or []
        self.story = story

    @property
    def name(self):
        return slugify(self.title.lower())

    @property
    def url(self):
        if self.story:
            return url_for('success_story', story=self.name)

    @property
    def logo(self):
        return 'images/success-stories/%s.webp' % self.name

    def __eq__(self, other):
        if isinstance(other, str):
            return self.name == other
        elif isinstance(other, Case):
            return self.name == other.name
        return NotImplemented


CASES = [
    Case(title="ALS Swiss",
        description="A society for people suffering ALS disease.",
        taglines=[
            "The Swiss ALS society improves its donation management "
            "thanks to Tryton",
            ],
        story=True),
    Case(title="APAR @ AIIMS",
        description="Annual Performance Appraisal for the All Indian "
        "Institute of Medical Sciences",
        story=True),
    Case(
        title="Advocate Consulting Legal Group",
        description="A legal firm servicing the general aviation industry",
        taglines=[
            "Law firms can also benefit from Tryton",
            ],
        story=True),
    Case(
        title="Banque Française Mutualiste",
        description="A French bank for the public service."),
    Case(
        title="Blue Box Distribution",
        description="An international distributor of hair care products.",
        taglines=[
            "Tryton helps to structure "
            "BLUE BOX Distribution's business processes",
            ],
        story=True),
    Case(
        title="Buchkontor Teltow",
        description="A bookstore with its on publishing house",
        taglines=[
            "Buchkontor Teltow uses the Tryton POS to sell books",
            ],
        story=True),
    Case(
        title="CAMIR",
        description="A provider of spare parts for machinery.",
        taglines=[
            "Tryton helps manufacturers like CAMIR reduce paper usage",
            ],
        story=True),
    Case(
        title="La Cave Thrace",
        description="Imports and distributes wine in France."),
    Case(
        title="Cultural Commons Collection Society",
        description="Collects and distributes music royalties."),
    Case(
        title="Expertise Vision",
        description="Produces vision based systems.",
        taglines=[
            "Expertise Vision has structured their purchasing process "
            "thanks to Tryton",
            ],
        story=True),
    Case(
        title="Felber",
        description="A stamp and signalisation company.",
        taglines=[
            "Tryton can handle Felber's huge amount of invoices",
            ],
        story=True),
    Case(
        title="GotSHO LIMS",
        description="Software Solution for genomic world.",
        taglines=[
            "Tryton's framework is used to develop a LIMS solution "
            "for genetics and diagnostics",
            ],
        story=True),
    Case(
        title="Grufesa",
        description="Exports strawberries in Europe.",
        taglines=[
            "Tryton helps Grufesa export berries to countries all around the "
            "world",
            ],
        story=True),
    Case(
        title="Inmedio Berlin",
        description="An institute specialising in conflict resolution.",
        taglines=[
            "Inmedio does their tax report without an external consultant "
            "thanks to Tryton",
            ],
        story=True),
    Case(
        title="Institut Mèdic per la Imatge",
        description="Provides all kinds of MRI scans, nuclear medicine "
        "and bone densitometry."),
    Case(
        title="Jordà",
        description="Installs and maintains lifts and elevators.",
        taglines=[
            "Tryton can be connected to an android application "
            "which can then add data in real time",
            ],
        story=True),
    Case(
        title="Koolvet",
        description="Software for veterinary clinics that deal with small "
        "domestic pets and larger farm animals.",
        taglines=[
            "Tryton powers a vertical solution for the veterinarian sector",
            ],
        story=True),
    Case(
        title="Lackierzentrum Reichenbach",
        description="Produces surface coating for automotive, aerospace, "
        "construction and mechanical engineering."),
    Case(
        title="Legna",
        description="Graphic design, digital printing "
        "and offset solution company",
        taglines=[
            "Legna uses Tryton to structure its digital printing process "
            "and improve its productivity",
            ],
        story=True),
    Case(
        title="MARKOM Offroad",
        description="An offroad driving school.",
        taglines=[
            "MARKOM replaced a proprietary legacy system "
            "with a free modern system including Tryton",
            ],
        story=True),
    Case(
        title="MenschensKinder Teltow",
        description="Operates municipal day care centers and "
        "parent-child groups."),
    Case(
        title="Mifarma",
        description="Leading online parapharmacy.",
        taglines=[
            "MiFarma delivers more than 2000 daily shipments thanks to Tryton",
            ],
        story=True),
    Case(
        title="Revelle",
        description="Consulting in developing countries and "
        "emerging economies.",
        taglines=[
            "The Revelle Group manages its energy "
            "and environmental projects with Tryton",
            ],
        story=True),
    Case(
        title="Sinclair Containers",
        description="Sells and rents containers.",
        story=True),
    Case(
        title="Skoda Autohaus Zeidler",
        description="A German car dealership and workshop for Skoda."),
    Case(
        title="Wenger Energie",
        description="A provider of vacuum degassing and filter systems.",
        taglines=[
            "Tryton manages Wenger Energie's 4 companies",
            ],
        story=True),
    ]


@app.route('/success-stories')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def success_stories():
    cases = sorted(
        sample(CASES, len(CASES)), key=attrgetter('story'), reverse=True)
    return render_template('success_stories.html.jinja', cases=cases)


@app.route('/business-cases.html', endpoint='success_stories-alt')
def success_stories_alt():
    return redirect(url_for('success_stories'))


@app.route('/success-stories/<story>')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def success_story(story):
    if story == '_':
        story = choice(CASES).name
    cases = [c for c in CASES if c.story or c.name == story]
    try:
        next_case = cases[(cases.index(story) + 1) % len(cases)]
    except ValueError:
        abort(HTTPStatus.NOT_FOUND)
    try:
        return render_template(
            'success_stories/%s.html.jinja' % story, next_case=next_case,
            canonical=url_for_canonical(story=story))
    except TemplateNotFound:
        abort(HTTPStatus.NOT_FOUND)


@app.route('/success-stories/<story>/tagline')
def success_story_tag_line(story):
    if story == '_':
        case = choice(list(filter(attrgetter('taglines'), CASES)))
        story = case.name
    else:
        try:
            case = CASES[CASES.index(story)]
        except ValueError:
            abort(HTTPStatus.NOT_FOUND)
    if not case.taglines:
        abort(HTTPStatus.NOT_FOUND)
    tagline = choice(case.taglines)
    return "\n".join(
        [tagline, url_for('success_story', story=story, _external=True)])


@sitemap.register_generator
def success_story_generator():
    for case in CASES:
        if case.url:
            yield 'success_story', dict(story=case.name)


@app.route('/demo')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def demo():
    return render_template('demo.html.jinja')


@app.route('/download')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def download():
    return render_template('download.html.jinja')


@app.route('/download.html', endpoint='download-alt')
def download_alt():
    return redirect(url_for('download'))


@app.route('/forum')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def forum():
    return render_template('forum.html.jinja')


@app.route('/presentations')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def presentations():
    return render_template('presentations.html.jinja')


@app.route('/papers.html', endpoint='presentations-alt')
def presentations_alt():
    return redirect(url_for('presentations'))


@app.route('/events/<event>')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def event(event):
    if event == '_':
        event = 'layout'

    class Day:
        def __init__(self, date, *events, location=None, full=False):
            if not isinstance(date, datetime.date):
                date = datetime.date(*date)
            self.date = date
            self.full = full
            self.location = location
            self.events = []
            for event in events:
                self.add(*event)

        def add(self, summary, start, end, *args, location=None):
            if not isinstance(start, datetime.time):
                start = datetime.time(*start)
            if not isinstance(end, datetime.time):
                end = datetime.time(*end)
            start = datetime.datetime.combine(self.date, start)
            end = datetime.datetime.combine(self.date, end)
            if not location:
                location = self.location
            self.events.append(Event(
                    summary, start, end, *args, location=location))

        @property
        def start(self):
            if self.events:
                return min(e.start for e in self.events)

        @property
        def end(self):
            if self.events:
                return max(e.end for e in self.events)

    class Event:
        def __init__(self, summary, start, end, description='', profiles=(),
                location=None):
            self.summary = summary
            self.start = start
            self.end = end
            self.location = location
            self.description = description
            self.profiles = [Profile(*p) for p in profiles]

    class Profile:
        def __init__(self, name, gravatar, company='', url=''):
            self.name = name
            self.gravatar = gravatar
            self.company = company
            self.url = url
    try:
        return render_template(
            'events/%s.html.jinja' % event, Day=Day,
            canonical=url_for_canonical(event=event))
    except TemplateNotFound:
        abort(HTTPStatus.NOT_FOUND)


@app.route('/contribute')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def contribute():
    return render_template('contribute.html.jinja')


@app.route('/how-to-contribute.html', endpoint='contribute-alt')
def contribute_alt():
    return redirect(url_for('contribute'))


@app.route('/develop')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def develop():
    return render_template('develop.html.jinja')


@app.route('/develop/guidelines/code')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def guidelines_code():
    return render_template('guidelines/code.html.jinja')


@app.route('/develop/guidelines/documentation')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def guidelines_documentation():
    return render_template('guidelines/documentation.html.jinja')


@app.route('/develop/guidelines/help-text')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def guidelines_documentation_help():
    return render_template('guidelines/help.html.jinja')


@app.route('/develop/guidelines/howto')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def guidelines_documentation_howto():
    return render_template('guidelines/howto.html.jinja')


@app.route('/foundation')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def foundation():
    return render_template('foundation.html.jinja')


@app.route('/foundation/', endpoint='foundation-alt')
def foundation_alt():
    return redirect(url_for('foundation'))


@cache.memoize(timeout=60 * 60 * 24)
def fetch_supporters():
    headers = {'Content-Type': 'application/json'}
    try:
        response = requests.get(SUPPORTERS_URL, headers=headers)
        return response.json()
    except Exception:
        app.logger.error('fail to fetch supporters', exc_info=True)
        return []


@app.route('/supporters')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def supporters():
    def url(supporter, start):
        for website in supporter['websites']:
            if website.startswith(start):
                return website
    return render_template('supporters.html.jinja',
        supporters=fetch_supporters(),
        discuss_url=partial(url, start='https://discuss.tryton.org/'),
        roundup_url=partial(url, start='https://bugs.tryton.org/'),
        heptapod_url=partial(url, start='https://foss.heptapod.net/'))


@app.route('/foundation/supporters.html', endpoint='supporters-alt')
def supporters_alt():
    return redirect(url_for('supporters'))


@cache.memoize(timeout=60 * 60 * 24)
def fetch_gravatar(hash, **params):
    url = 'https://secure.gravatar.com/avatar/' + hash
    response = requests.get(url, params=params)
    response.raise_for_status()
    rv = make_response(response.content)
    rv.content_type = response.headers['Content-Type']
    rv.cache_control.max_age = 60 * 60 * 24
    rv.cache_control.public = True
    return rv


@app.route('/avatar/<hash>')
@cache.cached(query_string=True)
def avatar(hash):
    if not set(request.args.keys()).issubset(set('sdr')):
        abort(HTTPStatus.BAD_REQUEST)
    if request.args.get('s'):
        try:
            if not (1 < int(request.args.get('s')) < 2048):
                abort(HTTPStatus.BAD_REQUEST)
        except ValueError:
            abort(HTTPStatus.BAD_REQUEST)
    if request.args.get('d') and request.args.get('d') not in {
            '404', 'mp', 'identicon', 'monsterid', 'wavatar', 'retro',
            'robohash', 'blank'}:
        abort(HTTPStatus.BAD_REQUEST)
    if request.args.get('r') and request.args.get('r') not in {
            'g', 'pg', 'r', 'x'}:
        abort(HTTPStatus.BAD_REQUEST)
    return fetch_gravatar(hash, **request.args)


@app.template_filter('hostname')
def hostname(url):
    return urlparse(url).hostname


@app.template_filter('url_local')
def url_local(url):
    return urlparse(url)._replace(scheme='', netloc='').geturl()


@cache.memoize(timeout=60 * 60 * 24)
def fetch_donators():
    headers = {'Content-Type': 'application/json'}
    try:
        response = requests.get(DONATORS_URL, headers=headers)
        return response.json()
    except Exception:
        app.logger.error('fail to fetch donators', exc_info=True)
        return []


@cache.memoize(timeout=60 * 60 * 24)
def fetch_donations():
    headers = {'Content-Type': 'application/json'}
    try:
        response = requests.get(DONATIONS_URL, headers=headers)
        return response.json()
    except Exception:
        app.logger.error('fail to fetch donations', exc_info=True)
        return []


@app.route('/donate')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def donate():
    return render_template('donate.html.jinja',
        donators=fetch_donators(),
        donations=fetch_donations())


@app.route('/foundation/donations.html', endpoint='donate-alt')
def donate_alt():
    return redirect(url_for('donate'))


@app.route('/donate/thanks')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def donate_thanks():
    return render_template('donate_thanks.html.jinja')


@app.route('/donate/cancel')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def donate_cancel():
    return render_template('donate_cancel.html.jinja')


class Service(enum.Flag):
    NONE = 0
    CONSULTING = enum.auto()
    DEVELOPMENT = enum.auto()
    HOSTING = enum.auto()
    TRAINING = enum.auto()


class Provider:
    def __init__(self, name, positions, services=Service.NONE):
        self.name = name
        self.positions = positions
        self.services = services

    def __getattr__(self, name):
        if self.services:
            return self.services & getattr(Service, name.upper())

    def __json__(self):
        return {
            'name': self.name,
            'positions': self.positions,
            }


PROVIDERS = [
    Provider(name="ACK",
        positions=[(43.29464884900557, -3.001523942912372)],
        services=Service.CONSULTING | Service.DEVELOPMENT | Service.TRAINING),
    Provider(name="Adiczion",
        positions=[(43.52153, 5.43150)],
        services=Service.CONSULTING | Service.DEVELOPMENT),
    Provider(name="B2CK",
        positions=[(50.631123, 5.567552)],
        services=Service.CONSULTING | Service.DEVELOPMENT | Service.TRAINING),
    Provider(name="Coopengo",
        positions=[(48.873278, 2.324776)],
        services=Service.DEVELOPMENT),
    Provider(name="Datalife",
        positions=[(37.9596885, -1.2086241)],
        services=Service.CONSULTING | Service.DEVELOPMENT),
    Provider(name="First Telecom",
        positions=[(38.0131591, 23.7721521)],
        services=Service.CONSULTING),
    Provider(name="gcoop",
        positions=[(-34.59675, -58.43035)],
        services=Service.CONSULTING | Service.DEVELOPMENT),
    Provider(name="IntegraPer",
        positions=[(-11.9753824, -77.0860785)],
        services=Service.CONSULTING | Service.DEVELOPMENT),
    Provider(name="INROWGA",
        positions=[(18.476389, -69.893333)],
        services=Service.CONSULTING),
    Provider(name="Kopen Software",
        positions=[(41.5995983, 0.5799085)],
        services=Service.CONSULTING | Service.DEVELOPMENT | Service.HOSTING
        | Service.TRAINING),
    Provider(name="Lampero",
        positions=[(44.4758631, 25.8231538)],
        services=Service.CONSULTING),
    Provider(name="Lava Lab Software",
        positions=[(-27.978905, 153.389466)],
        services=Service.CONSULTING | Service.DEVELOPMENT),
    Provider(name="m-ds",
        positions=[(52.520008, 13.404954)],
        services=Service.CONSULTING | Service.DEVELOPMENT | Service.HOSTING
        | Service.TRAINING),
    Provider(name="NaN-tic",
        positions=[(41.544063, 2.115122)],
        services=Service.CONSULTING | Service.DEVELOPMENT),
    Provider(name="power solutions",
        positions=[(47.0467674, 8.3048232)],
        services=Service.CONSULTING | Service.DEVELOPMENT | Service.HOSTING),
    Provider(name="SISalp",
        positions=[(45.903956, 6.099937), (43.132028, 5.935532)],
        services=Service.CONSULTING | Service.HOSTING),
    Provider(name="Virtual Things",
        positions=[(48.13585, 11.577415), (50.775116, 6.083565)],
        services=Service.CONSULTING | Service.DEVELOPMENT | Service.TRAINING),
    Provider(name="Wuerfel Datentechnik",
        positions=[(49.24776, 8.87911)],
        services=Service.CONSULTING | Service.DEVELOPMENT | Service.TRAINING),
    ]


@app.route('/service-providers')
@cache.cached(key_prefix=cache_key_prefix_view, query_string=True)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def service_providers():
    providers = PROVIDERS.copy()
    shuffle(providers)
    services = []
    environ = {}
    filters = {'consulting', 'development', 'hosting', 'training'}
    if not (request.args.keys() <= filters):
        abort(HTTPStatus.BAD_REQUEST)
    for filter_name in filters:
        environ[filter_name] = request.args.get(filter_name, type=int)
        if (environ[filter_name] is not None
                and environ[filter_name] not in {0, 1}):
            abort(HTTPStatus.BAD_REQUEST)
        if environ[filter_name]:
            services.append(getattr(Service, filter_name.upper()))
    if services:
        services = functools.reduce(operator.ior, services)
        providers = list(
            filter(lambda p: (p.services & services) == services, providers))
    return render_template(
        'service_providers.html.jinja', providers=providers, **environ)


@app.route('/services.html', endpoint='service_providers-alt')
def service_providers_alt():
    return redirect(url_for('service_providers'))


@app.route('/service-providers/start')
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def service_providers_start():
    return render_template('service_providers_start.html.jinja')


@app.route('/favicon.ico')
def favicon():
    return redirect(url_for('static', filename='images/favicon.ico'))


@app.route('/_warmup')
def warmup():
    fetch_news_items()
    fetch_events()
    for supporter in fetch_supporters():
        hash = hashlib.md5(supporter['email'].encode('utf-8')).hexdigest()
        try:
            fetch_gravatar(
                hash, s='198', d=gravatar.default, r=gravatar.rating)
        except Exception:
            app.logger.warning('fail to fetch gravatar')
    for path in glob.glob(os.path.join(app.static_folder, '**/*.webp')):
        dominant_color(os.path.relpath(path, app.static_folder))
    return '', HTTPStatus.NO_CONTENT


@app.errorhandler(HTTPStatus.NOT_FOUND)
@cache.cached(key_prefix=cache_key_prefix_view)
@add_links(PRECONNECT_HEADERS + JS_LINK_HEADERS + CSS_LINK_HEADERS)
def not_found(error):
    return render_template(
        'not_found.html.jinja', canonical=None), HTTPStatus.NOT_FOUND


class RequestFormatter(logging.Formatter):
    def format(self, record):
        record.url = request.url
        record.remote_addr = request.remote_addr
        return super().format(record)


mail_handler = SMTPHandler(
    mailhost='mx.tryton.org',
    fromaddr='www@tryton.org',
    toaddrs=['webmaster@tryton.org'],
    subject="[www.tryton.org] Application Error",
    )
mail_handler.setLevel(logging.ERROR)
formatter = RequestFormatter(
    '[%(asctime)s] %(remote_addr)s requested %(url)s\n'
    '%(levelname)s in %(module)s: %(message)s'
    )
default_handler.setFormatter(formatter)
mail_handler.setFormatter(formatter)

if __name__ == '__main__':
    app.config['CDN_DEBUG'] = ast.literal_eval(
        os.environ.get('CDN_DEBUG', 'True'))
    app.run(debug=ast.literal_eval(os.environ.get('DEBUG', 'True')))

if not app.debug:
    app.logger.addHandler(mail_handler)
