
# Description
* Created by Larry on 2017-06-20, automatically & regularly AMI update & notification based on AWS services
* This method can be used for any AMIs, not just limited to Windows, modify `Automation` document for different uses

## Workflow
* Cloudwatch trigger
	* Regular trigger for AMI update (create automation job)
	* Event trigger when automation job status changed (Success, Failed, TimedOut, Cancelled)
* Based on the event passed by Cloudwatch, script determine next move (Send alert, share AMI)

![alt text](https://github.com/LarrysGIT/AWS-Managed-AMI/blob/master/Images/workflow.png)

```
*** POC specified environment variable values START ***
# Lambda function lookup last built AMI based on AMI_LOOKUP_PATTERN, if nothing found, DEFAULT_AMI_ID will be used.
DEFAULT_AMI_ID: 2016: ami-3bb4a958 # 2012: ami-77bba614
# Send build result via SNS arn
ALERT_ARN1: 'arn:xxxxxxxxxxxxxxx'
# Share AMI ID among AWS accounts
AMI_SHARE_ACCOUNTS: 'awsaccountnumber1', 'awsaccountnumber2'
# Specify platform of current build, will be used in message content
PLATFORM: 2016
# Lookup the latest build AMI via name pattern
AMI_LOOKUP_PATTERN: AMI_Auto_Update_*
# Automation document name, lamba will launch this document to update AMI
AUTOMATION_NAME: AMI-Windows-Update-2016
# This role is used by SMS automation document
PROFILE_ROLE: AMI-Patching-Profile
# This role is used by SMS automation document
AUTOMATION_ROLE: arn:automationrole
# Subnet ID to put instance
AMI_SUBNET: subnet-xxxxxxx
# Instance Tag: Owner
TAG_OWNER: Larry
# Instance Tag: Description
TAG_DESCRIPTION: Amazon managed AMI update - POC
# Target AMI name
TARGET_AMI_NAME: AMI_Auto_Update_Larry_{{global:DATE_TIME}}
*** POC specified environment variable values END ***
```

## AWS Services and use
* EC2, SSM (Automation job and AMI)
* Cloudwatch (Logging, trigger and monitoring)
* SNS (Notification service, e.g. email)
* Lambda (Python, core)

### ami-update.py

* Deploy in Lambda

* Choose a Lambda role with suffient privileges

* http://docs.aws.amazon.com/systems-manager/latest/userguide/automation-simpatch.html#automation-pet2

### AMI-Windows-Update.json

* Deploy in SMS

* https://ap-southeast-2.console.aws.amazon.com/ec2/v2/home?region=ap-southeast-2#Documents:Owner=MeOrAmazon;sort=Name

* Setup roles: http://docs.aws.amazon.com/systems-manager/latest/userguide/automation-setup.html

-- Larry.Song@outlook.com



