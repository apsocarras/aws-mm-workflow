import boto3
import io
import zipfile
import datetime
import os
import json

s3 = boto3.client('s3')

def lambda_handler(event, context):
  bucket = event['Records'][0]['s3']['bucket']['name']
  object_key = event['Records'][0]['s3']['object']['key']
    
  # Get timestamp for folder name
  timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    
  # Read the zip file
  zip_file = s3.get_object(Bucket=bucket, Key=object_key)['Body'].read()
    
  # Extract the files from the zip file and upload them to S3
  with io.BytesIO(zip_file) as zip_stream:
    with zipfile.ZipFile(zip_stream) as zip_file:
      for file_name in zip_file.namelist():
        if not file_name.endswith('/'):  # Ignore subdirectories
          file_contents = zip_file.read(file_name)
          key_name = f"uploads/{timestamp}/{os.path.basename(file_name)}"
          s3.put_object(Bucket=bucket, Key=key_name, Body=file_contents)
    
  # Remove zip file from the bucket once unzipped   
  s3.delete_object(Bucket=bucket, Key=object_key)
  
  return {
    'statusCode': 200,
    'body': json.dumps(
    {'Bucket': f'{bucket}', 
    'Zipfile': f'{object_key}', 
    'Extracted_to': f'uploads/{timestamp}'
    })
  }
