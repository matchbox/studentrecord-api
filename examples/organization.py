from pprint import pprint
import studentrecord

sr = studentrecord.StudentRecord(('USERNAME', 'PASSWORD'))
customer = sr.customer[0]

print 'Setting customer to', customer['name']
sr.choose_customer(customer)

print 'All organizations:'
pprint(list(sr.organization))
print

print 'Creating test organization:'
data = sr.organization.create(
    name='Test Organization',
    location={'city': 'Boston',
              'state': 'MA',
              'country': 'USA'})
pprint(data)
print

print 'Updating the name:'
sr.organization[data] = dict(
    name='Different Name',
    location={'city': 'Akron'})
pprint(data)
print

print 'Getting the organization by ID:'
pprint(sr.organization[data['id']])
print

print 'Filtering...'
pprint(list(sr.organization.filter(name='Different Name')))
print

print 'Deleting...'
del sr.organization[data]

print 'remaining objects:'
pprint(list(sr.organization))
