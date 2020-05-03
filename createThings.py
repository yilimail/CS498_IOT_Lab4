################################################### Connecting to AWS
import boto3
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient
import json
################################################### Create random name for things
import random
import string

################################################### Parameters for Thing
thingArn = ''
thingId = ''
#thingName = ''.join([random.choice(string.ascii_letters + string.digits) for n in xrange(15)])
defaultPolicyName = 'Lab4_policy'
###################################################

def createThing(i):
    global thingClient
    thingName = ''.join([random.choice(string.ascii_letters + string.digits) for n in range(15)])
    thingResponse = thingClient.create_thing(
        thingName = thingName
    )
    data = json.loads(json.dumps(thingResponse, sort_keys=False, indent=4))
    for element in data:
        if element == 'thingArn':
            thingArn = data['thingArn']
        elif element == 'thingId':
            thingId = data['thingId']
        createCertificate(thingName, i)
    return thingName

def createCertificate(thingName, i):
    global thingClient
    certResponse = thingClient.create_keys_and_certificate(
    	setAsActive = True
    )
    data = json.loads(json.dumps(certResponse, sort_keys=False, indent=4))
    for element in data:
        if element == 'certificateArn':
            certificateArn = data['certificateArn']
        elif element == 'keyPair':
            PublicKey = data['keyPair']['PublicKey']
            PrivateKey = data['keyPair']['PrivateKey']
        elif element == 'certificatePem':
            certificatePem = data['certificatePem']
        elif element == 'certificateId':
            certificateId = data['certificateId']

    publicName = "certificates/thing_{}.public.key".format(i)
    privateName = "certificates/thing_{}.private.pem".format(i)
    certName = "certificates/thing_{}.certificate.pem".format(i)

    with open(publicName, 'w') as outfile:
        outfile.write(PublicKey)
    with open(privateName, 'w') as outfile:
        outfile.write(PrivateKey)
    with open(certName, 'w') as outfile:
        outfile.write(certificatePem)

    response = thingClient.attach_policy(
        policyName = defaultPolicyName,
        target = certificateArn
    )
    response = thingClient.attach_thing_principal(
        thingName = thingName,
        principal = certificateArn
    )

thingClient = boto3.client('iot')

for i in range(500):
    name = createThing(i)
    thingClient.add_thing_to_thing_group(thingGroupName="lab4", thingName=name)
    print("Created Thing ", i)
