#!/bin/env python3
import datetime

import requests
from flask import Flask, render_template, redirect
from flask_caching import Cache
from flask_rev import Rev
from icalendar import Calendar
from lxml import objectify, html

NEWS_URL = 'https://discuss.tryton.org/c/news'
CALENDAR_URL = 'https://calendar.google.com/calendar/embed?src=p4jhgp9j5a2ehndebdglo6tslg%40group.calendar.google.com&ctz=Europe%2FBrussels'
CALENDAR_ICS = 'https://calendar.google.com/calendar/ical/p4jhgp9j5a2ehndebdglo6tslg%40group.calendar.google.com/public/basic.ics'

cache = Cache(config={'CACHE_TYPE': 'simple'})
app = Flask(__name__)
cache.init_app(app)
Rev(app)


@app.route('/')
@cache.cached(timeout=60 * 60)
def index():
    return render_template(
        'index.html',
        news=list(news_items(3)),
        next_events=next_events(3))


@app.context_processor
def inject_menu():
    menu = {
        'Tryton': [
            ('Success Stories', '#'),
            ('Get Tryton', '#'),
            ('Documentation', '//docs.tryton.org/'),
            ],
        'Community': [
            ('Forum', 'https://discuss.tryton.org/'),
            ('Presentations', '#'),
            ('Contribute', '#'),
            ],
        'Foundation': [
            ('About', '#'),
            ('Supporters', '#'),
            ('Donations', '#'),
            ],
        'Services': [
            ('Service providers', '#'),
            ('Become a service provider', '#'),
            ],
        }
    return dict(menu=menu)


@app.context_processor
def inject_copyright_dates():
    return dict(copyright_dates='2008-%s' % datetime.date.today().year)


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


if __name__ == '__main__':
    app.run(debug=True)
