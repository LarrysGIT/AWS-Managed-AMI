from __future__ import print_function

## Larry created on 2017-06-15 and updated on 2017-06-21 for regularly Windows AMI auto update
## Deploy in lambda
## Trigger event json {"Event": "AMI_Update_Startup"}
## Sample data:

'''
Workflow:
 - Cloudwatch trigger
     * Regular trigger for AMI update (create automation job)
     * Event trigger when automation job status changed (Success, Failed, TimedOut, Cancelled)
 - Based on the event passed by Cloudwatch, script determine next actions (Send alert, share AMI)

AWS Services:
 - EC2, SSM (Automation job and AMI)
 - Cloudwatch (Logging and trigger)
 - SNS (Notification service, like email)
 - Lambda (Python)
'''

import boto3
import os
import json
import re
import time
from datetime import datetime
import urllib
import xml.etree.ElementTree as ET
import logging

def lambda_handler(event, context):
    logging.getLogger().setLevel(logging.INFO)
    logging.info('AMI auto update triggered')

    global strDate
    global ALERT_ARNS, AMI_SHARE_ACCOUNTS, DEFAULT_AMI_ID, PLATFORM, AMI_LOOKUP_PATTERN, AUTOMATION_NAME, PROFILE_ROLE, AUTOMATION_ROLE, AMI_SUBNET, TARGET_AMI_NAME, TAG_OWNER, TAG_DESCRIPTION, S3_PATH

    strDate = datetime.utcnow().strftime('%Y-%m-%d')
    # Automation document name
    # If AUTOMATION_NAME not set, script doesn't know which automation document to use
    AUTOMATION_NAME = os.getenv('AUTOMATION_NAME')
    if not AUTOMATION_NAME:
        logging.error('Please set AUTOMATION_NAME environment variable')
        raise ValueError('Please set AUTOMATION_NAME environment variable')

    # Windows version prefix
    # If PLATFORM not set, script doesn't know it's a 2012 or 2016 AMI
    PLATFORM = os.getenv('PLATFORM')
    if not PLATFORM:
        logging.error('Please set PLATFORM environment variable')
        raise ValueError('Please set PLATFORM environment variable')

    # AMI automatic lookup pattern
    # If AMI_LOOKUP_PATTERN not set, script not be able to search AMI
    AMI_LOOKUP_PATTERN = os.getenv('AMI_LOOKUP_PATTERN')
    if not AMI_LOOKUP_PATTERN:
        logging.info('AMI_LOOKUP_PATTERN not set, script use DEFAULT_AMI_ID instead')

    # Profile role attach to instance
    # If PROFILE_ROLE not set, automation job failed
    PROFILE_ROLE = os.getenv('PROFILE_ROLE')
    if not PROFILE_ROLE:
        logging.error('PROFILE_ROLE not set')
        raise ValueError('Please set PROFILE_ROLE environment variable')

    # Automation role pass to automation job
    # If AUTOMATION_ROLE not set, automation job failed
    AUTOMATION_ROLE = os.getenv('AUTOMATION_ROLE')
    if not AUTOMATION_ROLE:
        logging.error('AUTOMATION_ROLE not set')
        raise ValueError('Please set AUTOMATION_ROLE environment variable')

    # Subnet to setup instance
    # If AMI_SUBNET not set, automation job failed
    AMI_SUBNET = os.getenv('AMI_SUBNET')
    if not AMI_SUBNET:
        logging.error('AMI_SUBNET not set')
        raise ValueError('Please set AMI_SUBNET environment variable')

    # TARGET_AMI_NAME to create new AMI name
    # If TARGET_AMI_NAME not set, automation job failed
    TARGET_AMI_NAME = os.getenv('TARGET_AMI_NAME')
    if not TARGET_AMI_NAME:
        logging.error('TARGET_AMI_NAME not set')
        raise ValueError('Please set TARGET_AMI_NAME environment variable')

    # TAG_OWNER to create new AMI name
    # If TAG_OWNER not set, please set owner of ami and instance
    TAG_OWNER = os.getenv('TAG_OWNER')
    if not TAG_OWNER:
        logging.error('TAG_OWNER not set, set to tag owner of ami and instance')
        raise ValueError('Please set TAG_OWNER environment variable')

    # S3_PATH to put new AMI ID
    # If S3_PATH not set, AMI ID not be able to upload to s3
    S3_PATH = os.getenv('S3_PATH')
    if not S3_PATH:
        logging.error('S3_PATH not set, set to put new AMI ID in S3')
        raise ValueError('Please set S3_PATH environment variable')
    else:
        global S3_BUCKET, S3_KEY
        try:
            S3_BUCKET, S3_KEY = re.search('^(.+):/(.+?)$', S3_PATH).groups()
        except:
            raise ValueError('Please set S3_PATH environment variable with corrent format "s3-bucket-name:/key1/key2/key3"')

    # TAG_DESCRIPTION to create new AMI name
    # If TAG_DESCRIPTION not set, tag blank
    TAG_DESCRIPTION = os.getenv('TAG_DESCRIPTION')

    ## Get environment variables
    # if ALERT_ARN not set, no notification will be sent
    ALERT_ARNS = [ os.environ[i] for i in os.environ.keys() if re.search('^ALERT_ARN\d*', i) ]
    ALERT_ARNS = [ i.strip() for i in ALERT_ARNS if i.strip() ]

    # if AMI_SHARE_ACCOUNTS not set, AMI will not be able to automatically share with other accounts
    AMI_SHARE_ACCOUNTS = os.getenv('AMI_SHARE_ACCOUNTS')
    if AMI_SHARE_ACCOUNTS:
        AMI_SHARE_ACCOUNTS = [ i.strip() for i in AMI_SHARE_ACCOUNTS.split(',')]
    # Script will retrieve a list of AMIs with name pattern Ami_Auto_Update_*
    # If the list is empty, script uses DEFAULT_AMI_ID to create new AMI
    # If DEFAULT_AMI_ID not set at this moment, script doesn't know what to do and quit
    DEFAULT_AMI_ID = os.getenv('DEFAULT_AMI_ID')
    if DEFAULT_AMI_ID:
        DEFAULT_AMI_ID = DEFAULT_AMI_ID.strip()


    #return Post_AMI_s3(amiid='ami-12345678', s3bucket=S3_BUCKET, key=S3_KEY)

    logging.info('Dump event for debugging: %s' % json.dumps(event))
    if event.get('Event') == 'AMI_Update_Startup':
        logging.info('This is a scheduled startup')
        return Startup()
    elif event.get('detail'):
        logging.info('This is a monitor for started automation job')
        if event.get('detail').get('Definition') != AUTOMATION_NAME:
            logging.info('This automation is not our concern')
            return 'The automation change is not our concern'
            pass
        # AMI-Windows-Update automation event captured
        # checkout status
        logging.info('Checking details of this automation job')
        return Automation_Status(event=event)
    else:
        return 'Unknown event'

## Check microsoft RSS for new updates
def LookupUpdate(ami_creationdate):
    # Comment below line to let script decide whether launch new ami job
    #return True
    try:
        ami_creationdate = datetime.strptime(ami_creationdate, '%Y-%m-%dT%H:%M:%S.%fZ')
        rss = ''
        r = urllib.urlopen('https://technet.microsoft.com/en-us/security/rss/bulletin')
        rss = ET.fromstring(r.read())
        r.close()
        latest_item = rss.find('channel').find('item')
        logging.info('The latest update found in RSS: [{}],[{}]'.format(latest_item.find('pubDate').text, latest_item.find('title').text))
        for i in rss.find('channel').findall('item'):
            if ami_creationdate < datetime.strptime(i.find('pubDate').text, '%Y-%m-%dT%H:%M:%S.%f0Z'):
                logging.info('Found an update later than AMI creation date: [{}],[{}]'.format(i.find('pubDate').text, i.find('title').text))
                logging.info('No need to scan more updates, going to launch an automation job')
                return True
        logging.info('No any updates later than ami creation date, ami has no updates to install')
        return False
    except Exception as e:
        logging.error(str(e))
        logging.error('RSS content not fetched')
    return True

## Based on name lookup pattern and default id, return the latest AMI ID
def Get_AMI():
    logging.info('')
    logging.info('Default AMI ID set: %s' % DEFAULT_AMI_ID)
    ## Get account id
    sts = boto3.client('sts')
    caller = sts.get_caller_identity()
    account_arn = caller['Arn']
    account_id = caller['Account']

    logging.info('Account ID running: %s' % account_arn)

    ami_togo = ''
    ec2 = boto3.client('ec2')
    if AMI_LOOKUP_PATTERN:
        ## Get existing images
        images = ec2.describe_images(
            Owners = [account_id],
            Filters = [{
                'Name': 'name',
                'Values': [AMI_LOOKUP_PATTERN]
            }]
        )
        if len(images['Images']) > 0:
            logging.info('AMI retrieved, count: %s' % len(images['Images']))
            images_sorted = sorted(images['Images'], key=lambda k: k['CreationDate'])
            logging.info('\n'.join(['Image name: %s' % i['Name'] for i in images_sorted]))
            ami_togo = images_sorted[-1]
            logging.info('Image picked for updating: [Name:%s][ID:%s]' % (ami_togo['Name'], ami_togo['ImageId']))

    if not ami_togo:
        logging.info('No images found, checking environment variable [DEFAULT_AMI_ID]')
        if DEFAULT_AMI_ID:
            try:
                ami_togo = ec2.describe_images(
                    ImageIds = [DEFAULT_AMI_ID]
                )
                ami_togo = ami_togo['Images'][0]
            except:
                pass
            if not ami_togo:
                logging.error('DEFAULT_AMI_ID can NOT be found, script quit!')
                return
        else:
            logging.error('Neither images nor DEFAULT_AMI_ID can be found, script quit!')
            return False
    return [ami_togo['ImageId'], ami_togo['CreationDate']]

## Scheduled trigger, start a new automation job
def Startup():
    ami_togo = ''
    ami_togo = Get_AMI()
    if ami_togo:
        logging.info('Base AMI to use: [{}],[{}]'.format(ami_togo[0], ami_togo[1]))
        if not LookupUpdate(ami_creationdate=ami_togo[1]):
            return 'There is no any update published in RSS'
    else:
        return 'No AMI can be used as template, script quit.'

    ami_id_togo = ami_togo[0]
    ## Trigger automation job
    logging.info('Final ami determined: %s' % ami_id_togo)
    ssm = boto3.client('ssm')
    
    response = ssm.start_automation_execution(
        DocumentName = AUTOMATION_NAME,
        Parameters = {
            'SourceAmiId': [ami_id_togo],
            'SubnetId': [AMI_SUBNET],
            'IamInstanceProfileName': [PROFILE_ROLE],
            'AutomationAssumeRole': [AUTOMATION_ROLE],
            'TargetAmiName': [TARGET_AMI_NAME],
            'Owner': [TAG_OWNER],
            'Description': [TAG_DESCRIPTION],
            'PreUpdateScript': ['Set-MpPreference -DisableRealtimeMonitoring $true -ErrorAction:SilentlyContinue']
        }
    )
    logging.info('Start new automation: %s' % str(response))
    logging.info('')
    return 'Automation job launched with ID: %s' % response['AutomationExecutionId']

## Get automation status and send SNS
def Automation_Status(event):
    status = event.get('detail').get('Status')
    status = status.lower()
    logging.info('Status is: %s' % status)

    message = Automation_Result(ExecutionID=event.get('detail').get('ExecutionId'))
    if status == 'success':
        message_subject = 'AWS AMI Autopatch Report for %s: Status: Success' % (PLATFORM)
    elif status == 'failed':
        message_subject = 'AWS AMI Autopatch Report for %s: Status: Failed' % (PLATFORM)
    elif status == 'cancelled':
        message_subject = 'AWS AMI Autopatch Report for %s: Status: Cancelled' % (PLATFORM)
    elif status == 'timedout':
        message_subject = 'AWS AMI Autopatch Report for %s: Status: TimedOut' % (PLATFORM)
    else:
        raise ValueError('Unknown status: [%s]' % status)
    
    if ALERT_ARNS and message:
        logging.info('Send alerts through sns')
        sns = boto3.client('sns')
        for i in ALERT_ARNS:
            response = sns.publish(TopicArn = i, Message = message, Subject = message_subject)
    else:
        logging.warning('Variable [ALERT_ARN*] not found or message content is blank, no need to send alert')

## Retrieve detailed automation results including new AMI id
def Automation_Result(ExecutionID):
    if not ExecutionID:
        return 'Execution ID is blank, why???'
    try:
        ssm = boto3.client('ssm')
        execution_result = ssm.get_automation_execution(AutomationExecutionId=ExecutionID)
        execution_result = execution_result.get('AutomationExecution')
        if execution_result['AutomationExecutionStatus'] == 'Success':
            ec2 = boto3.client('ec2')
            Image = ec2.describe_images(
                ImageIds = [execution_result['Outputs']['CreateImage.ImageId'][0]]
            )
            Post_AMI_s3(amiid=execution_result['Outputs']['CreateImage.ImageId'][0], s3bucket=S3_BUCKET, key=S3_KEY)
            result = [
                '\n',
                'The scheduled patching of AWS AMI has completed: Please find below new AMI details for general use.'
                '\n',
                '* New AMI ID:\t[%s]' % execution_result['Outputs']['CreateImage.ImageId'][0],
                '* New AMI Name:\t[%s]' % Image['Images'][0]['Name'],
                '* Overall result:\t[%s]' % execution_result['AutomationExecutionStatus'],
                '* Document name:\t[%s]' % execution_result['DocumentName'],
                '* Execution ID:\t[%s]' % ExecutionID,
                '\n',
                Post_AMI(amiid=execution_result['Outputs']['CreateImage.ImageId'][0], userids=AMI_SHARE_ACCOUNTS),
                '\n',
                'Below components have updated:',
                ' - Windows updates',
                ' - AWSPowerShell',
                ' - AWS SSM agent',
                ' - EC2Config / EC2Launch',
                ' - AWSPVDriver',
                ' - AWSCloudFormationHelperScripts',
                '\n'
            ]
        else:
            # automation job failed, remove instance
            try:
                Step_LaunchInstance = ''
                Step_LaunchInstance = [step for step in execution_result['StepExecutions'] if step['StepName'] == 'LaunchInstance']
                if Step_LaunchInstance:
                    Step_LaunchInstance = Step_LaunchInstance[0]
                    InstanceId = Step_LaunchInstance['Outputs'].get('InstanceIds')
                    if InstanceId:
                        InstanceId = InstanceId[0]
                    if re.search('(?i)^i-[a-z0-9]+?$', InstanceId):
                        print('Instance to be terminated: %s' % InstanceId)
                        ec2 = boto3.client('ec2')
                        ec2.terminate_instances(
                            InstanceIds = [InstanceId]
                        )
            except Exception as e:
                print(str(e))
                pass
            Step_CheckUpdates = ''
            Step_CheckUpdates = [step for step in execution_result['StepExecutions'] if step['StepName'] == 'CheckUpdates']
            if Step_CheckUpdates:
                Step_CheckUpdates = Step_CheckUpdates[0]
                if Step_CheckUpdates['StepStatus'] == 'Failed':
                    return False
            result = [
                '\n',
                "The scheduled patching of AWS AMI has failed: Please investigate further via AWS console."
                '\n',
                '* New AMI ID:\t[]',
                '* New AMI Name:\t[]',
                '* Overall result:\t[%s]' % execution_result['AutomationExecutionStatus'],
                '* Document name:\t[%s]' % execution_result['DocumentName'],
                '* Execution ID:\t[%s]' % ExecutionID,
                '\n',
                'AMI Not shared: [No AMI ID]',
                '\n'
            ]
        return '\n'.join(result)
    except:
        return 'Unable to get automation results, why???'

## Share AMI through accounts
def Post_AMI(amiid, userids):
    if re.search('(?i)^ami-\w+?$', amiid):
        try:
            ec2 = boto3.client('ec2')
            r = ec2.modify_image_attribute(
                ImageId = amiid,
                OperationType = 'add',
                Attribute = 'launchPermission',
                UserIds = userids
            )
            logging.info('AMI [%s] shared with accounts: %s' % (amiid, userids))
            return 'AMI [%s] shared with accounts: %s' % (amiid, userids)
        except Exception as e:
            logging.error('AMI not shared: %s' % str(e))
            return 'AMI not shared: %s' % str(e)
    else:
        logging.error('AMI not shared: [No AMI ID]')
        return 'AMI not shared: [No AMI ID]'

## Write AMI ID to s3
def Post_AMI_s3(amiid, s3bucket, key):
    if re.search('(?i)^ami-\w+?$', amiid):
        try:
            s3 = boto3.client('s3')
            if key.endswith('/'):
                key = '{}{}.txt'.format(key, amiid)
            r = s3.put_object(
                ACL = 'bucket-owner-full-control',
                Bucket = s3bucket,
                Key = key,
                Body = amiid
            )
            logging.info('AMI ID [%s] put into s3: %s %s' % (amiid, s3bucket, key))
            return 'AMI ID [%s] put into s3: %s %s' % (amiid, s3bucket, key)
        except Exception as e:
            logging.error('AMI ID not put to s3: %s' % str(e))
            return 'AMI ID not put to s3: %s' % str(e)
    else:
        logging.error('AMI ID not write to s3: [No AMI ID]')
        return 'AMI ID not write to s3: [No AMI ID]'
