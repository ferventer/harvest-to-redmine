# /usr/bin/env python


'''HarvestToRedmine.

Usage:
    harvesttoredmine [options]
    harvesttoredmine sync (today|yesterday|week | --date <date>)

Options:
  -h --help          Show this screen.
  --version          Show the version.
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
    redmine_activities = [activity.name for activity in redmine_client.time_entry_activities]
    nf_redmine_activities = set(harvest_activities) - set(redmine_activities)

    if nf_redmine_activities:
        raise ValueError('Cant find these Harvest activity types in redmine {}'.format(nf_redmine_activities))
    else:
        return True


def _log_day_entries_to_redmine(day_entry, in_date, redmine_client, harvest_client):
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
        ticket_id = 37080
        entry_notes = day_entry['notes']

    issue = redmine_client.issues[ticket_id]

    try:
        redmine_client.time_entries.new(issue=issue, activity=day_entry['task'],
                                        spent_on=in_date.strftime('%Y-%m-%d'), user=redmine_client.user,
                                        hours=day_entry['hours'], comments=entry_notes)
    except Exception as err:
        return "Failed", ticket_id, err, bcolors.RED

    if day_entry['notes'] == '':
        day_entry['notes'] = 'Logged'
    else:
        day_entry['notes'] += ' Logged'

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


def parse_date(password, config, args):
    in_date = datetime.today()

    if args['--date']:
        if args[1].count('/') == 1:
            for day in xrange(1, 32):
                sync_hours(password, config, datetime.datetime(datetime.datetime(year=int(str.split('/')[1]),
                                                                                 month=int(str.split('/')[0]),
                                                                                 day=day)))
    if args['yesterday']:
        in_date = in_date - timedelta(1)
    if args['week']:
        start_week = in_date - timedelta(in_date.weekday())
        for delta in range(0, 4):
            sync_hours(start_week + timedelta(days=delta))
    sync_hours(password, config, in_date)


def sync_hours(password, config, in_date):
    in_date_time = in_date.timetuple()

    doy = in_date_time.tm_yday

    try:
        harvest_client = Harvest(config.get('harvest', 'url'), config.get('harvest', 'email'), password)
    except Exception as err:
        print "There is a problem with connecting to Harvest: {0}".format(err)
        return

    try:
        redmine_client = Redmine(config.get('redmine', 'url'), config.get('redmine', 'key'))
    except Exception as err:
        print "There is a problem with connecting to Redmine: {0}".format(err)

    day = harvest_client.get_day(doy, in_date.year)

    try:
        _check_activities_compability(redmine_client, config.get('harvest', 'activities'))
    except ValueError as err:
        print err.message
        return

    day_entries = filter(lambda entry: entry.get('notes') != 'Logged', day.get('day_entries', []))

    sync_table = _table_init()
    rows = [_table_header()]
    for day_entry in tqdm(day_entries, total=len(day_entries), leave=True):
        time_entry = _log_day_entries_to_redmine(day_entry, in_date, redmine_client, harvest_client)
        rows.append([in_date.strftime('%d-%m-%Y'), str(time_entry[1]), str(day_entry.get('hours')),
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
    if args['sync']:
        parse_date(password, config, args)


if __name__ == '__main__':
    main()
