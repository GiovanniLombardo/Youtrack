from youtrack.connection import Connection as yt

dst_uri = 'http://127.0.0.1:8080'
dst_loc = dict(token='perm:YWRtaW4=.NDQtMA==.V1Wb9gabpdd0teLz7x8t4wvKwG3o5H')

inst = yt(dst_uri, **dst_loc)
for prj in inst.getProjectIds():
    for issue in inst.getIssues(prj, '', '', ''):
        print(issue)
        if issue.attachments:
            input('There are attachments')
            for attachment in issue.attachments:
                print(type(attachment), attachment)