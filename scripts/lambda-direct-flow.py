import pandas as pd 
import numpy as np
import json
import os
import re
import logging
import boto3
from io import StringIO

## --- S3 --- ##

s3 = boto3.client('s3')

def s3_upload_df(df:pd.DataFrame, full_key:str) -> None:
  csv_buffer = StringIO()
  df.to_csv(csv_buffer, index=False)
  s3.put_object(Bucket=BUCKET_NAME, Key=full_key, Body=csv_buffer.getvalue().encode())

## --- Logging --- ##

logger = logging.getLogger()
logger.setLevel(logging.INFO)

## --- Environment Variables (Max total size: 4KB) --- ##
# Could also access these values from lambda-unzip.py payload

BUCKET_NAME = os.environ["BUCKET_NAME"].strip()
DATA_FOLDER = os.environ["DATA_FOLDER"].strip()
ID_COL = os.environ["ID_COL"].strip()
DB = os.environ["DB"].strip()

with open("schema.json", "r") as f:
  SCHEMA = json.load(f)

## For testing this function locally: 
# BUCKET_NAME = "pet-adoption-mm"
# DATA_FOLDER = "uploads"
# ID_COL = "PetID"
# DB = "my_database"

# SCHEMA = {"Type": "int64",
#  "Name": "object",
#  "Age": "int64",
#  "Breed1": "int64",
#  "Breed2": "int64",
#  "Gender": "int64",
#  "Color1": "int64",
#  "Color2": "int64",
#  "Color3": "int64",
#  "MaturitySize": "int64",
#  "FurLength": "int64",
#  "Vaccinated": "int64",
#  "Dewormed": "int64",
#  "Sterilized": "int64",
#  "Health": "int64",
#  "Quantity": "int64",
#  "Fee": "int64",
#  "State": "int64",
#  "RescuerID": "object",
#  "VideoAmt": "int64",
#  "Description": "object",
#  "PetID": "object",
#  "PhotoAmt": "float64",
#  "File": "object"}  

# Filter for certain file types
IMG_TYPES = set(x.strip().lstrip(".") for x in os.environ["IMG_TYPES"])
TAB_TYPES = set(x.strip().lstrip(".") for x in os.environ["TAB_TYPES"])

## For testing this function locally: 
# IMG_TYPES = {"jpg", "jpeg", "png"}
# TAB_TYPES = {"csv", "tsv"}

if len(IMG_TYPES.difference({"jpg", "jpeg", "png"})) > 0 or len(IMG_TYPES) == 0:
  IMG_TYPES = {"jpg", "jpeg", "png"}
  logger.warning(f"Invalid IMG_TYPES filter ({IMG_TYPES}) -- using defaults ({IMG_TYPES}) ")
  
if len(TAB_TYPES.difference({"csv", "tsv"})) > 0  or len(TAB_TYPES) == 0: 
  TAB_TYPES = {"csv", "tsv"}
  logger.warning(f"Invalid TAB_TYPES filter ({TAB_TYPES}) -- using defaults ({TAB_TYPES})")
  
FILE_TYPES = IMG_TYPES.union(TAB_TYPES)
  
## Get list of new uploads (new_object_basenames)

response = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=DATA_FOLDER)
folders = set(obj['Key'].split("/")[1] for obj in response['Contents'])
folders.discard("") # blank element created by "DATA_FOLDER/" in the list 
new_folder = max(folders)
new_object_basenames = [os.path.basename(obj["Key"]) for obj in response["Contents"] if obj['Key'].split("/")[1] == new_folder]

## Check for unexpected file types

unexpected_file_types = set(obj.split(".")[-1] for obj in new_object_basenames).difference(set(FILE_TYPES)) 
if len(unexpected_file_types) > 0: 
  logger.warning(f"Ignoring ({(', ').join(unexpected_file_types)}) files in {new_folder}/ -- expected only {(', ').join(FILE_TYPES)}.")
  new_object_basenames = [obj for obj in new_object_basenames if obj.split(".")[-1] in FILE_TYPES]        

## Get tabular data 

tabular_data = []
for file in new_object_basenames:
  if file.split(".")[-1] not in TAB_TYPES: 
      continue
  else:
    response = s3.get_object(Bucket=BUCKET_NAME, Key=f"{DATA_FOLDER}/{new_folder}/{file}")
    body = response['Body']
    csv_string = body.read().decode('utf-8')
    data = pd.read_csv(StringIO(csv_string))
  
    # Check for schema conflicts
    schema_conflicts = []
    for col, col_type in data.dtypes.items():
      # Wrong column
      if col not in SCHEMA.keys():
        schema_conflicts.append({col:"Not in schema"})
      # Wrong column type
      elif str(col_type) != SCHEMA[col]:
        schema_conflicts.append({col:{"exp":SCHEMA[col], "got":str(col_type)}})
  
    if len(schema_conflicts) > 0: 
      logger.warning(f"Schema conflicts in {new_folder}/{file}: {schema_conflicts}. Ignoring file.")
      continue
    else:
      data['File'] = file
      tabular_data.extend(data.to_dict(orient="records"))

df = pd.DataFrame(tabular_data)          

# Check for duplicates in ID_COL  
dup_rows = df[df.duplicated(subset=[ID_COL])]
if not dup_rows.empty:
  logger.warning(f"{len(dup_rows)} duplicate rows across {list(dup_rows['File'].unique())}.")
  
  # Write to s3
  s3_upload_df(dup_rows, full_key=f"{DATA_FOLDER}/{new_folder}/errors/source_duplicates.csv")
  
  df.drop_duplicates(ignore_index=True, subset=[ID_COL], inplace=True)   
  logger.info(f"Wrote {len(dup_rows)} duplicate rows to s3 bucket and dropped from dataframe.")

# Fill NaNs  
# Generic string fill:  df.fillna({col:"None" for col in SCHEMA.keys() if SCHEMA[col] == "object"}, axis=1, inplace=True)
# Generic numeric fill: df.fillna({col:round(df[col].mean()) for col in SCHEMA.keys() if SCHEMA[col] != "object"}, axis=1, inplace=True)

df.fillna({"Name":"Unnamed", "Description":"No description"}, inplace=True)

# Join with image filenames: df["Image"] 
image_filenames = [obj for obj in new_object_basenames if obj.split(".")[-1] in IMG_TYPES]
image_ids = [file.split(".")[0] for file in image_filenames] 

image_df = pd.DataFrame({"Image": image_filenames, ID_COL: image_ids}).set_index(ID_COL) 
df = df.merge(image_df, how = "left", left_on=ID_COL, right_index=True)

## TO-DO: Query database for records with ID_COL in image_ids or in df[ID_COL]

# --- Placeholder Query --- #  
match_result = dict() 
match_tab_ids = [x[ID_COL] for x in match_result if x[ID_COL] in df[ID_COL]]
match_image_ids = [x[ID_COL] for x in match_result if x[ID_COL] in image_ids]
# --- # 

if len(match_tab_ids) > 0:
  if not UPDATE: 
    logger.warning(F"{len(match_tab_ids)} rows have {ID_COL} already in {DB}")
    dup_rows_db = df[df[ID_COL].isin(match_tab_ids)]
    
    s3_upload_df(dup_rows_db, full_key=f"{DATA_FOLDER}/{new_folder}/errors/db_duplicates.csv")
    df = df[~df.index.isin(dup_rows_db.index)] 

  else: 
    logger.info(f"Updating {len(match_tab_ids)} records in {DB}")
    update_rows_db = df[df[ID_COL].isin(match_tab_ids)]

if len(match_image_ids) > 0:
  if not UPDATE: 
    logger.warning(F"{len(match_image_ids)} images match {ID_COL} already in {DB}")
    image_ids = [x for x in image_ids if x not in match_image_ids] # Drop 
  else: 
    logger.info(f"Updating {len(match_image_ids)} in {DB}")
    # TO-DO: Log match_image_ids (INFO)
  
## Direct data flow to models (images vs no images)

df.drop('File', axis=1, inplace=True) # Column not present when model was trained 

# Has Images --> MMIM   
s3_upload_df(df[~df['Image'].isna()], full_key="tmp/mmim.csv")

# No Images --> NIM
s3_upload_df(df[df['Image'].isna()], full_key="tmp/nim.csv")
