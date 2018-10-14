#!/bin/env python3
from collections import namedtuple, OrderedDict
from random import shuffle
import datetime

import requests
from flask import Flask, render_template, redirect, url_for
from flask_caching import Cache
from flask_htmlmin import HTMLMIN
from flask_compress import Compress
from flask_rev import Rev
from icalendar import Calendar
from lxml import objectify, html

NEWS_URL = 'https://discuss.tryton.org/c/news'
CALENDAR_URL = 'https://calendar.google.com/calendar/embed?src=p4jhgp9j5a2ehndebdglo6tslg%40group.calendar.google.com&ctz=Europe%2FBrussels'
CALENDAR_ICS = 'https://calendar.google.com/calendar/ical/p4jhgp9j5a2ehndebdglo6tslg%40group.calendar.google.com/public/basic.ics'

cache = Cache(config={'CACHE_TYPE': 'simple'})
app = Flask(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = datetime.timedelta(days=365)
app.config['MINIFY_PAGE'] = True
app.config['CACHE_DEFAULT_TIMEOUT'] = 60 * 60
cache.init_app(app)
Compress(app)
HTMLMIN(app)
Rev(app)


HEART = '<span class="material-icons" style="color:#d9534f;">favorite</span>'


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
        ('Forum', 'https://discuss.tryton.org/'),
        ('Presentations', url_for('presentations')),
        ('Contribute', '#'),
        ]
    menu['Foundation'] = [
        ('About', '#'),
        ('Supporters', '#'),
        (HEART + ' Donations', '#'),
        ]
    menu['Services'] = [
        ('Service providers', '#'),
        ('Become a service provider', '#'),
        ]
    return dict(menu=menu)


@app.context_processor
def inject_copyright_dates():
    return dict(copyright_dates='2008-%s' % datetime.date.today().year)


@app.context_processor
def inject_heart():
    return dict(heart=HEART)


@app.route('/news/index.html')
@app.route('/news')
def news():
    return redirect(NEWS_URL)


def news_items(size=-1):
    rss = requests.get(NEWS_URL + '.rss')
    root = objectify.fromstring(rss.content)
    for item in root.xpath('/rss/channel/item')[:size]:
        yield item


@app.template_filter('blockquote')
def blockquote(content):
    block = html.fromstring(str(content)).find('blockquote')
    for box in block.find_class('lightbox-wrapper'):
        box.drop_tree()
    return block.text_content()


@app.route('/events.html')
@app.route('/events')
def events():
    return redirect(CALENDAR_URL)


def next_events(size=-1):
    today = datetime.date.today()
    ics = requests.get(CALENDAR_ICS)
    cal = Calendar.from_ical(ics.content)

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
@cache.cached()
def success_stories():
    Case = namedtuple('Case', 'title description url logo'.split())
    cases = [
        Case(
            title="AMMEBA",
            description="A Mutual of Medical Federation of Buenos Aires.",
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
            description="Offers all kinds of MRI scans, nuclear medicine and "
            "bone densitometry.",
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
@cache.cached()
def download():
    return render_template('download.html')


@app.route('/presentations')
@cache.cached()
def presentations():
    return render_template('presentations.html')


if __name__ == '__main__':
    app.run(debug=True, extra_files=['templates'])
