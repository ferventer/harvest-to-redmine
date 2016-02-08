from sys import argv
from getpass import getpass
from harvest import Harvest
from time import strptime
from datetime import date
import redmine
from local_settings import HARVEST_URL_ROOT, HARVEST_USER_EMAIL, REDMINE_URL_ROOT, REDMINE_API_KEY, CLIENT_NAME


def sync_hours_for_date(password, date_str):
    in_date = strptime(date_str, '%d/%m/%Y')
    doy = in_date.tm_yday

    print "Syncing %d/%d/%d (%s)" % (in_date.tm_mday, in_date.tm_mon, in_date.tm_year, doy)

    h = Harvest(HARVEST_URL_ROOT, HARVEST_USER_EMAIL, password)
    rm = redmine.Redmine(REDMINE_URL_ROOT, key=REDMINE_API_KEY
    rm_date = date(*in_date[:3])
    rm_users = rm.users
    rm_user = rm_users[6]
    day = h.get_day(doy, 2016)
    activities = rm.time_entry_activities
    development = None
    meeting = None
    proj_man = None
    for activity in activities:
        if activity.name == 'Development':
            development = activity
        elif activity.name == 'Meeting':
            meeting = activity
        if activity.name == 'Project Management':
            proj_man = activity

    if development is None or meeting is None or proj_man is None:
        raise ValueError('Cant find all activity types')

    at_map = {'Coding': development, 'Meeting': meeting, 'Project Management': proj_man}

    for day_entry in day['day_entries']:
        if day_entry['client'] != CLIENT_NAME:
            continue
        activity = at_map.get(day_entry['task'])
        if not activity:
            print "Can't map activity '%s'" % day_entry['task']
            continue
        if day_entry['notes'] is not None and 'logged' in day_entry['notes'].lower():
            continue
        elif day_entry['notes'] is None:
            day_entry['notes'] = ''

        if activity == development or day_entry['notes'].startswith('#'):
            if day_entry['notes'].startswith('#'):
                try:
                    ticket_id = int(day_entry['notes'][1:])
                except (TypeError, ValueError):
                    print "Can't parse ID on %s" % day_entry['notes']
                    continue
            entry_notes = ''
        else:
            print "Not logging {}".format(day_entry['notes'])
            continue

        issue = rm.issues[ticket_id]
        try:
            te = rm.time_entries.new(issue=issue, activity=activity, spent_on=rm_date.strftime('%Y-%m-%d'), user=rm_user, hours=day_entry['hours'], comments=entry_notes)
        except Exception as e:
            print e.read()
            return
        if day_entry['notes'] == '':
            day_entry['notes'] = 'Logged'
        else:
            day_entry['notes'] += ' Logged'

        try:
            h.update(day_entry['id'], day_entry)
        except Exception as e:
            print "Failed to save time for %d. Delete manually" % ticket_id
            return
        print "Logged %02f hours for #%d" % (day_entry['hours'], ticket_id)


def main():
    password = getpass()

    if argv[1].count('/') == 1:
        for i in xrange(1, 32):
            sync_hours_for_date(password, '%d/%s' % (i, argv[1]))
    else:
        sync_hours_for_date(password, argv[1])


if __name__ == '__main__':
    main()
