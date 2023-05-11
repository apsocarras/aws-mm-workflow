
# Lack of directory-level events in AWS EventBridge makes two things difficult about processing multiple files together: 
# A. Telling Lambda which files are part of a single upload job
# B. Waiting till an entire folder of objects is uploaded before processing
#   (e.g. 5 minute step function timer won't work -- it will still get triggered for every object that gets created in the bucket)

# Three Solutions: 

## -------------------------------------------- ###

# 1. Upload files as a single .zip --> single object-level event trigger:
# Need another lambda function to extract first before continuing pipeline  
  # To scale, need to increase base limits on memory and/or temporary storage (costs)
  # Requires the least set up on the part of the uploader.

## -------------------------------------------- ###

# 2. Timestamped filenames (A.) + Manually trigger function after upload completes (B.)
# Requires an upload script or manual triggering from the command line

## Command line: After uploading, run: 
# aws lambda invoke \
#     --function-name mm_direct_flow \
#     --invocation-type Event \
#     --payload '{"bucket_name": BUCKET_NAME, "directory_name":f"uploads/{timestamp}"} 

## Upload script (.py): 

import boto3 
import os
import json
import logging
from datetime import datetime as dt

SOURCE_DIRECTORY = "test"
BUCKET_NAME = 'pet-adoption-mm'
UPDATE = False 

## --- Logging --- ###

# Create logger
logger = logging.getLogger('mm_upload.py')
logger.setLevel(logging.DEBUG)

# Create console handler and set level to INFO
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)

# Add handlers to logger
logger.addHandler(console_handler)

## --- S3 Upload ---  ###

s3 = boto3.client('s3')

response = s3.list_objects_v2(Bucket=BUCKET_NAME)
s3_basenames = [obj['Key'].split("/")[-1] for obj in response['Contents']]

to_upload = []
for dirpath, dirnames, filenames in os.walk(SOURCE_DIRECTORY):
  for filename in filenames:
    if filename in s3_basenames:
      if UPDATE:
        logger.info(f"Will upload updated {filename}")
      else:
        logger.debug(f"{filename} already exists in S3")
    else:
      filepath = os.path.join(dirpath, filename)
      to_upload.append(filepath)

timestamp = dt.strftime(dt.now(), format="%m-%d-%Y_%H-%M-%S")

for filepath in to_upload:
  filename = os.path.basename(filepath)
  try: 
    with open(filepath, "rb") as f:
      s3.upload_fileobj(f, BUCKET_NAME, f"uploads/{timestamp}/{filename}")
      logger.info(f"Uploaded {filename} successfully")
  except:
    logger.debug(f"Error uploading {filepath}")

## Manually invoke Lambda Function
lambda_client = boto3.client("lambda")
response = lambda_client.invoke(
    FunctionName='mm_direct_flow',
    InvocationType='Event', 
    Payload={"bucket_name":BUCKET_NAME, "directory_name":f"uploads/{timestamp}"}
)

## -------------------------------------------- ###

# 3. Timestamped folders + special file indicating upload size (upload_size.json)
# When upload_size.json is created, Lambda is triggered and reads the number of files to expect
# It loops and periodically counts the number of files in the new directory and waits till all have been uploaded before continuing
  # More flexible: Can be implemented within an upload script...

upload_size = json.dumps({"n_files":len(to_upload)})
s3.put_object(Bucket=BUCKET_NAME, Key=f"uploads/{timestamp}/upload_size.json", Body=upload_size)

  # ...Or without an upload script
  # Include timestamp in folder name you're uploading 
  # Include upload_size.json in upload folder 

## E.g. Counting Lambda Function

import json
import os
import time 
import boto3 

BUCKET_NAME = os.environ["BUCKET_NAME"].strip()
UPLOAD_FOLDER = os.environ["UPLOAD_FOLDER"].strip()

s3 = boto3.client("s3")
lambda_client = boto3.client("lambda")

def lambda_handler(event, context):

  # Identify newest upload folder 
  response = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=UPLOAD_FOLDER)
  folders = set(obj['Key'].split("/")[1] for obj in response['Contents'])
  folders.discard("") # blank element created by "UPLOAD_FOLDER/" in the list 
  new_folder = max(folders)

  # Read upload_size.json for number of files to expect 
  response = s3.get_object(Bucket=BUCKET_NAME, Key=f"{UPLOAD_FOLDER}/{new_folder}/upload_size.json")
  json_data = response['Body'].read().decode('utf-8')
  data_dict = json.loads(json_data)
  n_files = data_dict["n_files"]

  while True:
    response = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=f"{UPLOAD_FOLDER}/{new_folder}")
    num_files = len(response['Contents'])

    if num_files == n_files:
        payload = {'bucket':BUCKET_NAME, 'directory':f"{UPLOAD_FOLDER}/{new_folder}"}
        lambda_client.invoke(FunctionName='mm_direct_flow', InvocationType='Event', Payload=json.dumps(payload))
        break
        
    time.sleep(30) # include a time-out value in configuration
