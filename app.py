#!/bin/env python3
import datetime
import logging

from collections import namedtuple, OrderedDict
from functools import partial
from logging.handlers import SMTPHandler
from random import shuffle
from urllib.parse import urlparse

import requests
from flask import (Flask, render_template, redirect, url_for, request,
    make_response)
from flask.logging import default_handler
from flask_caching import Cache
from flask_compress import Compress
from flask_gravatar import Gravatar
from flask_htmlmin import HTMLMIN
from flask_rev import Rev
from flask_sitemap import Sitemap
from icalendar import Calendar
from lxml import objectify, html

NEWS_URL = 'https://discuss.tryton.org/c/news'
CALENDAR_URL = 'https://calendar.google.com/calendar/embed?src=p4jhgp9j5a2ehndebdglo6tslg%40group.calendar.google.com&ctz=Europe%2FBrussels'
CALENDAR_ICS = 'https://calendar.google.com/calendar/ical/p4jhgp9j5a2ehndebdglo6tslg%40group.calendar.google.com/public/basic.ics'
SUPPORTERS_URL = 'https://foundation.tryton.org:9000/foundation/foundation/1/supporters'
DONATORS_URL = 'https://foundation.tryton.org:9000/foundation/foundation/1/donators?account=732&account=734'
DONATIONS_URL = 'https://foundation.tryton.org:9000/foundation/foundation/1/donations?account=732&account=734'

PROVIDERS = [
    ('Adiczion', [(43.52153, 5.43150)]),
    ('B2CK', [(50.631123, 5.567552)]),
    ('Coopengo', [(48.873278, 2.324776)]),
    ('Datalife', [(37.9596885, -1.2086241)]),
    ('First Telecom', [(38.0131591, 23.7721521), (44.83722, 20.40560)]),
    ('gcoop', [(-34.59675, -58.43035)]),
    ('Lava Lab Software', [(-27.978905, 153.389466)]),
    ('m-ds', [(52.520008, 13.404954)]),
    ('NaN-tic', [(41.544063, 2.115122)]),
    ('SISalp', [(45.903956, 6.099937), (43.132028, 5.935532)]),
    ('Virtual Things', [(48.13585, 11.577415), (50.775116, 6.083565)]),
    ]

cache = Cache(config={'CACHE_TYPE': 'simple'})
app = Flask(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = datetime.timedelta(days=365)
app.config['MINIFY_PAGE'] = True
app.config['CACHE_DEFAULT_TIMEOUT'] = 60 * 60
app.config['SITEMAP_INCLUDE_RULES_WITHOUT_PARAMS'] = True
app.config['SITEMAP_VIEW_DECORATORS'] = [cache.cached()]
app.config['SITEMAP_IGNORE_ENDPOINTS'] = [
    'news-alt', 'news_rss', 'event-alt', 'success_stories-alt', 'download-alt',
    'presentations-alt', 'contribute-alt', 'foundation-alt', 'supporters-alt',
    'donate-alt', 'donate_thanks', 'donate_cancel', 'service_providers-alt']
cache.init_app(app)
Compress(app)
HTMLMIN(app)
Rev(app)
Gravatar(app, size=198, default='mp', use_ssl=True)
sitemap = Sitemap(app=app)


@app.after_request
def add_cache_control_header(response):
    if 'Cache-Control' not in response.headers:
        response.cache_control.max_age = app.config['CACHE_DEFAULT_TIMEOUT']
        response.cache_control.public = True
    return response


HEART = ('<span '
    'class="material-icons" '
    'style="color:#d9534f; font-size: inherit; vertical-align: middle">'
    'favorite'
    '</span>')


@app.route('/')
@cache.cached()
def index():
    return render_template(
        'index.html',
        news=list(news_items(3)),
        next_events=next_events(3))


@app.context_processor
def inject_menu():
    menu = OrderedDict()
    menu['Tryton'] = [
        ('Success Stories', url_for('success_stories')),
        ('Get Tryton', url_for('download')),
        ('Documentation', '//docs.tryton.org/'),
        ]
    menu['Community'] = [
        ('Forum', url_for('forum')),
        ('Presentations', url_for('presentations')),
        ('Contribute', url_for('contribute')),
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
def static_from_root():
    response = make_response(render_template('robots.txt'))
    response.mimetype = 'text/plain'
    return response


@app.route('/news')
@app.route('/news/index.html', endpoint='news-alt')
def news():
    return redirect(NEWS_URL)


@app.route('/news.rss')
@app.route('/rss.xml')
def news_rss():
    return redirect(NEWS_URL + '.rss')


def news_items(size=-1):
    try:
        rss = requests.get(NEWS_URL + '.rss')
        root = objectify.fromstring(rss.content)
    except Exception:
        app.logger.error('fail to fetch news', exc_info=True)
        return
    for item in root.xpath('/rss/channel/item')[:size]:
        yield item


@app.template_filter('blockquote')
def blockquote(content):
    block = html.fromstring(str(content)).find('blockquote')
    for box in block.find_class('lightbox-wrapper'):
        box.drop_tree()
    return block.text_content()


@app.route('/events')
@app.route('/events.html', endpoint='events-alt')
def events():
    return redirect(CALENDAR_URL)


def next_events(size=-1):
    today = datetime.date.today()
    try:
        ics = requests.get(CALENDAR_ICS)
        cal = Calendar.from_ical(ics.content)
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


@app.route('/success-stories')
@app.route('/business-cases.html', endpoint='success_stories-alt')
@cache.cached()
def success_stories():
    Case = namedtuple('Case', 'title description url logo'.split())
    cases = [
        Case(
            title="AMMEBA",
            description="A Medical Mutual Society from Buenos Aires.",
            url='',
            logo='images/success-stories/ammeba.jpg'),
        Case(
            title="Advocate Consulting",
            description="A legal firm servicing the general aviation industry",
            url='',
            logo='images/success-stories/advocate-consulting-legal.jpg'),
        Case(
            title="Banque Française Mutualiste",
            description="A French bank for the public service.",
            url='',
            logo='images/success-stories/bfm.jpg'),
        Case(
            title="La Cave Thrace",
            description="Imports and distributes wine in France.",
            url='',
            logo='images/success-stories/la-cave-thrace.jpg'),
        Case(
            title="Cultural Commons Collection Society",
            description="Collects and distributes music royalties.",
            url='',
            logo='images/success-stories/c3s.jpg'),
        Case(
            title="Grufesa",
            description="Exports strawberries in Europe.",
            url='',
            logo='images/success-stories/grufesa.jpg'),
        Case(
            title="Expertise Vision",
            description="Produces vision based systems.",
            url='',
            logo='images/success-stories/expertise-vision.jpg'),
        Case(
            title="Institut Mèdic per la Imatge",
            description="Provides all kinds of MRI scans, nuclear medicine "
            "and bone densitometry.",
            url='',
            logo='images/success-stories/imi.jpg'),
        Case(
            title="MenschensKinder Teltow",
            description="Operates municipal day care centers and "
            "parent-child groups.",
            url='',
            logo='images/success-stories/menschenskinder-teltow.jpg'),
        Case(
            title="Lackierzentrum Reichenbach",
            description="Produces surface coating for automotive, aerospace, "
            "construction and mechanical engineering.",
            url='',
            logo='images/success-stories/lackierzentrum-reichenbach.jpg'),
        Case(
            title="Lozärner Fasnachtskomitee",
            description="Organizes the Lucerne Carnival.",
            url='',
            logo='images/success-stories/lucerne-carnival.jpg'),
        Case(
            title="Revelle Group",
            description="Consulting in developing countries and "
            "emerging economies.",
            url='',
            logo='images/success-stories/revelle.jpg'),
        Case(
            title="Sinclair Containers",
            description="Sells and rents containers.",
            url='',
            logo='images/success-stories/sinclair-containers.jpg'),
        Case(
            title="Skoda Autohaus Zeidler",
            description="A German car dealership and workshop for Skoda.",
            url='',
            logo='images/success-stories/zeidler.jpg'),
        ]
    shuffle(cases)
    return render_template('success_stories.html', cases=cases)


@app.route('/download')
@app.route('/download.html', endpoint='download-alt')
@cache.cached()
def download():
    return render_template('download.html')


@app.route('/forum')
@cache.cached()
def forum():
    return render_template('forum.html')


@app.route('/presentations')
@app.route('/papers.html', endpoint='presentations-alt')
@cache.cached()
def presentations():
    return render_template('presentations.html')


@app.route('/events/<event>')
@cache.cached()
def event(event):
    class Day:
        def __init__(self, date, *events):
            if not isinstance(date, datetime.date):
                date = datetime.date(*date)
            self.date = date
            self.events = []
            for event in events:
                self.add(*event)

        def add(self, summary, start, end, *args):
            if not isinstance(start, datetime.time):
                start = datetime.time(*start)
            if not isinstance(end, datetime.time):
                end = datetime.time(*end)
            start = datetime.datetime.combine(self.date, start)
            end = datetime.datetime.combine(self.date, end)
            self.events.append(Event(summary, start, end, *args))

        @property
        def start(self):
            if self.events:
                return min(e.start for e in self.events)

        @property
        def end(self):
            if self.events:
                return max(e.end for e in self.events)

    class Event:
        def __init__(self, summary, start, end, description='', profiles=()):
            self.summary = summary
            self.start = start
            self.end = end
            self.description = description
            self.profiles = [Profile(*p) for p in profiles]

    class Profile:
        def __init__(self, name, gravatar, company='', url=''):
            self.name = name
            self.gravatar = gravatar
            self.company = company
            self.url = url
    return render_template('events/%s.html' % event, Day=Day)


@app.route('/contribute')
@app.route('/how-to-contribute.html', endpoint='contribute-alt')
@cache.cached()
def contribute():
    return render_template('contribute.html')


@app.route('/develop')
@cache.cached()
def develop():
    return render_template('develop.html')


@app.route('/foundation')
@app.route('/foundation/', endpoint='foundation-alt')
@cache.cached()
def foundation():
    return render_template('foundation.html')


@app.route('/supporters')
@app.route('/foundation/supporters.html', endpoint='supporters-alt')
@cache.cached()
def supporters():
    def url(supporter, start):
        for website in supporter['websites']:
            if website.startswith(start):
                return website
    headers = {'Content-Type': 'application/json'}
    try:
        response = requests.get(SUPPORTERS_URL, headers=headers)
        supporters = response.json()
    except Exception:
        app.logger.error('fail to fetch supporters', exc_info=True)
        supporters = []
    return render_template('supporters.html',
        supporters=supporters,
        discuss_url=partial(url, start='https://discuss.tryton.org/'),
        roundup_url=partial(url, start='https://bugs.tryton.org/'))


@app.template_filter('hostname')
def hostname(url):
    return urlparse(url).hostname


@app.route('/donate')
@app.route('/foundation/donations.html', endpoint='donate-alt')
@cache.cached()
def donate():
    headers = {'Content-Type': 'application/json'}
    try:
        response = requests.get(DONATORS_URL, headers=headers)
        donators = response.json()
    except Exception:
        app.logger.error('fail to fetch donators', exc_info=True)
        donators = []
    try:
        response = requests.get(DONATIONS_URL, headers=headers)
        donations = response.json()
    except Exception:
        app.logger.error('fail to fetch donations', exc_info=True)
        donations = []
    return render_template('donate.html',
        donators=donators,
        donations=donations)


@app.route('/donate/thanks')
@cache.cached()
def donate_thanks():
    return render_template('donate_thanks.html')


@app.route('/donate/cancel')
@cache.cached()
def donate_cancel():
    return render_template('donate_cancel.html')


@app.route('/service-providers')
@app.route('/services.html', endpoint='service_providers-alt')
@cache.cached()
def service_providers():
    shuffle(PROVIDERS)
    return render_template('service_providers.html', providers=PROVIDERS)


@app.route('/service-providers/start')
@cache.cached()
def service_providers_start():
    return render_template('service_providers_start.html')


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
    app.run(debug=True, extra_files=[
            'templates',
            'templates/service_providers',
            'templates/events',
            ])

if not app.debug:
    app.logger.addHandler(mail_handler)
