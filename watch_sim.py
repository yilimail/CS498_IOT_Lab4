# /*
# * Copyright 2010-2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# *
# * Licensed under the Apache License, Version 2.0 (the "License").
# * You may not use this file except in compliance with the License.
# * A copy of the License is located at
# *
# *  http://aws.amazon.com/apache2.0
# *
# * or in the "license" file accompanying this file. This file is distributed
# * on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# * express or implied. See the License for the specific language governing
# * permissions and limitations under the License.
# */


import os
import sys
import time
import uuid
import json
import logging
import argparse
from AWSIoTPythonSDK.core.greengrass.discovery.providers import DiscoveryInfoProvider
from AWSIoTPythonSDK.core.protocol.connection.cores import ProgressiveBackOffCore
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient
from AWSIoTPythonSDK.exception.AWSIoTExceptions import DiscoveryInvalidRequestException


AllowedActions = ['both', 'publish', 'subscribe']

# General message notification callback
def customOnMessage(message):
    print('Received message on topic %s: %s\n' % (message.topic, message.payload))

MAX_DISCOVERY_RETRIES = 10
GROUP_CA_PATH = "./groupCA/"

# Read in command-line parameters
parser = argparse.ArgumentParser()
parser.add_argument("-e", "--endpoint", action="store", required=True, dest="host", help="Your AWS IoT custom endpoint")
parser.add_argument("-r", "--rootCA", action="store", required=True, dest="rootCAPath", help="Root CA file path")
parser.add_argument("-c", "--cert", action="store", dest="certificatePath", help="Certificate file path")
parser.add_argument("-k", "--key", action="store", dest="privateKeyPath", help="Private key file path")
parser.add_argument("-n", "--thingName", action="store", dest="thingName", default="Bot", help="Targeted thing name")
parser.add_argument("-t", "--topic", action="store", dest="topic", default="sdk/test/Python", help="Targeted topic")
parser.add_argument("-m", "--mode", action="store", dest="mode", default="both",
                    help="Operation modes: %s"%str(AllowedActions))
parser.add_argument("-M", "--message", action="store", dest="message", default="Hello World!",
                    help="Message to publish")

args = parser.parse_args()
host = args.host
rootCAPath = args.rootCAPath
certificatePath = args.certificatePath
privateKeyPath = args.privateKeyPath
clientId = args.thingName
thingName = args.thingName
topic = args.topic

if args.mode not in AllowedActions:
    parser.error("Unknown --mode option %s. Must be one of %s" % (args.mode, str(AllowedActions)))
    exit(2)

if not args.certificatePath or not args.privateKeyPath:
    parser.error("Missing credentials for authentication, you must specify --cert and --key args.")
    exit(2)

if not os.path.isfile(rootCAPath):
    parser.error("Root CA path does not exist {}".format(rootCAPath))
    exit(3)

if not os.path.isfile(certificatePath):
    parser.error("No certificate found at {}".format(certificatePath))
    exit(3)

if not os.path.isfile(privateKeyPath):
    parser.error("No private key found at {}".format(privateKeyPath))
    exit(3)

# Configure logging
#logger = logging.getLogger("AWSIoTPythonSDK.core")
#logger.setLevel(logging.DEBUG)
#streamHandler = logging.StreamHandler()
#formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
#streamHandler.setFormatter(formatter)
#logger.addHandler(streamHandler)

# Progressive back off core
backOffCore = ProgressiveBackOffCore()

# Discover GGCs
discoveryInfoProvider = DiscoveryInfoProvider()
discoveryInfoProvider.configureEndpoint(host)
discoveryInfoProvider.configureCredentials(rootCAPath, certificatePath, privateKeyPath)
discoveryInfoProvider.configureTimeout(10)  # 10 sec

retryCount = MAX_DISCOVERY_RETRIES
discovered = False
groupCA = None
coreInfo = None
while retryCount != 0:
    try:
        discoveryInfo = discoveryInfoProvider.discover(thingName)
        caList = discoveryInfo.getAllCas()
        coreList = discoveryInfo.getAllCores()

        # We only pick the first ca and core info
        groupId, ca = caList[0]
        coreInfo = coreList[0]
        #print("Discovered GGC: %s from Group: %s" % (coreInfo.coreThingArn, groupId))

        #print("Now we persist the connectivity/identity information...")
        groupCA = GROUP_CA_PATH + groupId + "_CA_" + str(uuid.uuid4()) + ".crt"
        if not os.path.exists(GROUP_CA_PATH):
            os.makedirs(GROUP_CA_PATH)
        groupCAFile = open(groupCA, "w")
        groupCAFile.write(ca)
        groupCAFile.close()

        discovered = True
        #print("Now proceed to the connecting flow...")
        break
    except DiscoveryInvalidRequestException as e:
        print("Invalid discovery request detected!")
        print("Type: %s" % str(type(e)))
        print("Error message: %s" % e.message)
        print("Stopping...")
        break
    except BaseException as e:
        print("Error in discovery!")
        print("Type: %s" % str(type(e)))
        print("Error message: %s" % e.message)
        retryCount -= 1
        print("\n%d/%d retries left\n" % (retryCount, MAX_DISCOVERY_RETRIES))
        print("Backing off...\n")
        backOffCore.backOff()

if not discovered:
    print("Discovery failed after %d retries. Exiting...\n" % (MAX_DISCOVERY_RETRIES))
    sys.exit(-1)

# Iterate through all connection options for the core and use the first successful one
myAWSIoTMQTTClient = AWSIoTMQTTClient(clientId)
myAWSIoTMQTTClient.configureCredentials(groupCA, privateKeyPath, certificatePath)
myAWSIoTMQTTClient.onMessage = customOnMessage

connected = False
for connectivityInfo in coreInfo.connectivityInfoList:
    currentHost = connectivityInfo.host
    currentPort = connectivityInfo.port
    #print("Trying to connect to core at %s:%d" % (currentHost, currentPort))
    myAWSIoTMQTTClient.configureEndpoint(currentHost, currentPort)
    try:
        myAWSIoTMQTTClient.connect()
        connected = True
        break
    except BaseException as e:
        print("Error in connect!")
        print("Type: %s" % str(type(e)))
        print("Error message: %s" % e.message)

if not connected:
    print("Cannot connect to core %s. Exiting..." % coreInfo.coreThingArn)
    sys.exit(-2)

# Successfully connected to the core
if args.mode == 'both' or args.mode == 'subscribe':
    myAWSIoTMQTTClient.subscribe(topic, 0, None)
time.sleep(2)

loopCount = 0
# while True:
#     if args.mode == 'both' or args.mode == 'publish':
#         message = {}
#         message['message'] = args.message
#         message['sequence'] = loopCount
#         messageJson = json.dumps(message)
#         myAWSIoTMQTTClient.publish(topic, messageJson, 0)
#         if args.mode == 'publish':
#             print('Published topic %s: %s\n' % (topic, messageJson))
#         loopCount += 1
#     time.sleep(1)

from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient
import time
import json
import pandas as pd
import datetime
import numpy as np
from threading import Lock

device_st = 0
device_end = 500

#Path to the dataset, modify this
data_path = "data/class_{}.csv"

#Path to your certificates, modify this
certificate_formatter = "certificates/thing_{}.certificate.pem"
key_formatter = "certificates/thing_{}.private.pem"


class MQTTClient:
	def __init__(self, device_id, cert, key):
		self.device_id = str(device_id)
		self.state = 0
		self.client = AWSIoTMQTTClient(self.device_id)
		self.client.configureEndpoint("a191olynvpydfg-ats.iot.us-west-2.amazonaws.com", 8883)
		self.client.configureCredentials("root-ca-cert.pem", key, cert)
		self.client.configureOfflinePublishQueueing(-1)  # Infinite offline Publish queueing
		self.client.configureDrainingFrequency(2)  # Draining: 2 Hz
		self.client.configureConnectDisconnectTimeout(10)  # 10 sec
		self.client.configureMQTTOperationTimeout(5)  # 5 sec
		self.client.onMessage = self.customOnMessage


	def customOnMessage(self,message):
		print("client {} received prediction {} \n".format(self.device_id, json.loads(message.payload)["prediction"]))
		self.client.disconnectAsync()


	# Suback callback
	def customSubackCallback(self,mid, data):
	    pass


	# Puback callback
	def customPubackCallback(self,mid):
	    pass


	def publish(self):
		self.client.connect()
		self.client.subscribeAsync(self.device_id, 1, ackCallback=self.customSubackCallback)

		index = np.random.randint(0, len(data[self.state]))
		payload = {
			"device_id": self.device_id,
			"class": str(self.state),
			"features": list(data[self.state].iloc[index].values)
		}
		self.client.publishAsync("data/heartbeat", json.dumps(payload), 0, ackCallback=self.customPubackCallback)





# Don't change the code below
print("wait")
lock = Lock()
data = []
for i in range(5):
	a = pd.read_csv(data_path.format(i))
	data.append(a)

clients = []
for device_id in range(device_st, device_end):
	client = MQTTClient(device_id,certificate_formatter.format(device_id,device_id) ,key_formatter.format(device_id,device_id))
	clients.append(client)



states_for_test = [3, 0, 0, 0, 4, 0, 0, 1, 0, 0, 0, 4, 4, 0, 0, 3, 2, 3, 0, 2, 0, 0, 0, 2, 0, 0, 0, 0, 0, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,\
 0, 0, 0, 4, 0, 4, 3, 0, 0, 3, 0, 2, 0, 0, 0, 3, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 0, 0, 0, 0, 0, 4, 0, 0, 0, 0, 0, 0, 0,\
  2, 4, 1, 0, 0, 0, 4, 0, 0, 0, 0, 0, 4, 0, 0, 0, 1, 0, 0, 0, 0, 4, 1, 4, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 0, 0, 0, 0,\
   0, 1, 0, 1, 0, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 1, 1, 0, 0, 0, 0, 0, 3, 0, 0, 0, 0, 0, 0, 0, 0, 4, 0,\
    0, 0, 4, 0, 2, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 2, 0, 0, 0, 0, 0, 0, 2, 0, 4, 0, 3, 0,\
     0, 4, 1, 0, 0, 0, 0, 0, 0, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 4, 0, 0, 0, 0, 0, 0, 0,\
      0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 4, 0, 0, 0, 0, 2, 0, 0, 0, 2, 0, 0, 4, 4, 0, 0, 0, 0, 0, 0, 2,\
       0, 1, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 4, 0, 0, 2, 0, 0, 0, 0,\
        0, 1, 2, 1, 0, 0, 4, 0, 0, 0, 0, 0, 0, 3, 0, 0, 0, 0, 0, 0, 4, 0, 0, 4, 1, 0, 3, 2, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0,\
         0, 0, 4, 4, 0, 0, 0, 4, 0, 0, 2, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 4, 0, 1, 2, 0, 0,\
          0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 3, 0, 0, 3, 0, 0, 4, 0, 0, 0, 0, 4, 0, 0, 0, 0, 0, 0, 4, 0, 0,\
           0, 4, 1, 1, 0, 0, 0, 1, 3, 2, 0, 0, 0, 0, 0, 4, 0, 0, 0, 0, 4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0,\
            2, 0, 2, 2, 0, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 4, 0, 0, 0, 0, 0, 0, 0, 4]

s1,s2,s3,s4 = [],[],[],[]
for i in range(device_st,device_end):
	if i < 500:
		clients[i].state = states_for_test[i]
		if states_for_test[i] == 1: s1.append(i)
		elif states_for_test[i] == 2: s2.append(i)
		elif states_for_test[i] == 3: s3.append(i)
		elif states_for_test[i] == 4: s4.append(i)


print("Users at state 1: ", s1)
print("Users at state 2: ", s2)
print("Users at state 3: ", s3)
print("Users at state 4: ", s4)



print("send now?")
x = input()
if x == "s":
	for i,c in enumerate(clients):
		c.publish()
elif x == "d":
	for c in clients:
		c.disconnect()
		print("All devices disconnected")
else:
	print("wrong key pressed")

time.sleep(10)
