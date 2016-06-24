# /usr/bin/env python

'''HarvestToRedmine.

    Usage:
        harvesttoredmine.py sync [--t|--y|--w|--d <date>]

    Options:
          --t                Sync issues for today, if you provide no arguments this is option by default
          --y                Sync issues for yesterday
          --w                Sync issues for whole last week from Monday to Friday
          --d                Sync issues for specific date, today by default
'''

from getpass import getpass
from harvest import Harvest
from datetime import datetime, timedelta
from redmine import Redmine
from docopt import docopt, DocoptExit
from tqdm import tqdm
import os
import ConfigParser
from texttable import Texttable, get_color_string, bcolors


def _check_activities_compability(redmine_client, harvest_activities):
    u"""
    Checks if all harvest activities are availiable in redmine.
    redmine aactivies currently:
        u'Development', u'Code Review', u'Design', u'Testing Execution', u'Testing Planning', u'Testing Reporting',
        u'UnitTest', u'Meeting', u'Scoping', u'Project Management', u'Research & Development', u'Development Planning',
        u'Deployment', u'Documentation', u'Retest', u'Work', u'Other'
    """
    harvest_activities = harvest_activities.split(',')
    redmine_activities = {activity.name: activity.id for activity in redmine_client.time_entry_activities}
    nf_redmine_activities = set(harvest_activities) - set(redmine_activities.keys())

    if nf_redmine_activities:
        raise ValueError('Cant find these Harvest activity types in redmine {}'.format(nf_redmine_activities))
    else:
        return redmine_activities


def _log_day_entries_to_redmine(day_entry, in_date, redmine_client, harvest_client, default_ticket, redmine_activities):
    if day_entry.get('client') != 'Yellow':
        return

    if day_entry['notes'] is None:
        day_entry['notes'] = ''

    if day_entry['notes'].startswith('#'):
        try:
            ticket_id = int(day_entry['notes'][1:])
            entry_notes = ''
        except (TypeError, ValueError):
            err = "Can't parse ID on %s" % day_entry['notes']
            return "Failed", '', err, bcolors.RED
    else:
        ticket_id = default_ticket
        entry_notes = day_entry['notes']

    issue = redmine_client.issues[ticket_id]
    activity = redmine_activities.get(day_entry['task'] or 'Development')

    try:
        redmine_client.time_entries.new(issue=issue, activity=activity,
                                        spent_on=in_date, user=redmine_client.user,
                                        hours=day_entry['hours'], comments=entry_notes)
    except Exception as err:
        return "Failed", ticket_id, err.message, bcolors.RED

    if day_entry['notes'] == '':
        day_entry['notes'] = 'logged'
    else:
        day_entry['notes'] += ' logged'

    try:
        harvest_client.update(day_entry['id'], day_entry)
    except Exception:
        err = "Failed to save time for %d. Delete manually." % ticket_id
        return "Failed", ticket_id, err, bcolors.RED

    return "Logged", ticket_id, '', bcolors.GREEN


def _table_init():
    table = Texttable()
    table.set_deco(Texttable.HEADER | Texttable.BORDER | Texttable.HLINES | Texttable.VLINES)
    table.set_cols_dtype(["t", "t", "f", "t", "f"])
    table.set_cols_align(['r', 'r', 'r', 'r', 'r'])
    table.set_cols_width([10, 10, 10, 10, 10])
    return table


def _table_header():
    return [get_color_string(bcolors.BLUE, "Date"),
            get_color_string(bcolors.BLUE, "Ticket"),
            get_color_string(bcolors.BLUE, "Time"),
            get_color_string(bcolors.BLUE, "Status"),
            get_color_string(bcolors.BLUE, "Err")]


def _rtime(time, res):
    return round(time / int(res), 2) * int(res) if res else time


def parse_date(password, config, args):
    in_dates = [datetime.today()]

    if args['--d']:
        if args[1].count('/') == 1:
            in_dates = []
            for day in xrange(1, 32):
                in_dates.append(datetime.datetime(datetime.datetime(year=int(str.split('/')[1]),
                                                                    month=int(str.split('/')[0]),
                                                                    day=day)))
        else:
            try:
                in_dates = [datetime.strptime(args[1], "%Y-%m-%d")]
            except ValueError:
                print "Wrong date, please use YYYY-MM-DD format."
                return
    if args['--y']:
        in_dates = [in_dates[0] - timedelta(1)]
    if args['--w']:
        start_week = in_dates[0] - timedelta(days=7 + in_dates[0].weekday())
        in_dates = []
        for delta in range(0, 4):
            in_dates.append(start_week + timedelta(days=delta))
    sync_hours(password, config, in_dates)


def get_harvest_entries(harvest_client, config, in_dates):
    day_entries = {}
    for in_date in in_dates:
        in_date_time = in_date.timetuple()
        doy = in_date_time.tm_yday
        day = harvest_client.get_day(doy, in_date.year)
        entries = filter(lambda entry: entry.get('notes') != 'logged', day.get('day_entries', []))
        if entries:
            day_entries[in_date.strftime("%Y-%m-%d")] = entries
    return day_entries


def sync_hours(password, config, in_dates):
    try:
        harvest_client = Harvest(config.get('harvest', 'url'), config.get('harvest', 'email'), password)
    except Exception as err:
        print "There is a problem with connecting to Harvest: {0}".format(err)
        return

    try:
        redmine_client = Redmine(config.get('redmine', 'url'), config.get('redmine', 'key'))
    except Exception as err:
        print "There is a problem with connecting to Redmine: {0}".format(err)

    default_ticket = config.get('redmine', 'default_ticket')

    try:
        redmine_activities = _check_activities_compability(redmine_client, config.get('harvest', 'activities'))
    except ValueError as err:
        print err.message
        return

    harvest_entries = get_harvest_entries(harvest_client, config, in_dates)
    round_time = config.get('redmine', 'round_time')

    for date, date_entries in harvest_entries.iteritems():
        print "Syncing days for {}".format(date)
        sync_table = _table_init()
        for day_entry in tqdm(date_entries, total=len(date_entries), leave=True):
            rows = [_table_header()]
            day_entry['hours'] = _rtime(day_entry.get('hours'), round_time)

            time_entry = _log_day_entries_to_redmine(day_entry, date, redmine_client, harvest_client,
                                                     default_ticket, redmine_activities)

            rows.append([date, str(time_entry[1]),
                         str(day_entry.get('hours')),
                         get_color_string(time_entry[3], time_entry[0]),
                         time_entry[2] or '--'])

        sync_table.add_rows(rows)
        print(sync_table.draw() + "\n")


def _harvest_auth():
    try:
        password = getpass("Please, enter your Harvest password: ")
    except Exception as err:
        print 'There is problem with harvest authentication: {}'.format(err)
        return
    return password


def _read_config():
    config = ConfigParser.RawConfigParser()
    curr_dir = os.path.dirname(os.path.abspath(__file__))
    config.read(os.path.join(curr_dir, 'rm_harvest.conf'))
    return config


def main():
    try:
        args = docopt(__doc__)
    except DocoptExit:
        print "You haven't specify any commands, please see output of help command"

    config = _read_config()
    password = _harvest_auth()
    parse_date(password, config, args)


if __name__ == '__main__':
    main()
