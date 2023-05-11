import os
import boto3 
import json
import pandas as pd 
from autogluon.multimodal import MultiModalPredictor
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn
from io import StringIO
from mangum import Mangum

app=FastAPI()
handler=Mangum(app)

s3 = boto3.client("s3")

def s3_upload_df(df:pd.DataFrame, full_key:str) -> None:
  csv_buffer = StringIO()
  df.to_csv(csv_buffer, index=False)
  s3.put_object(Bucket=BUCKET_NAME, Key=full_key, Body=csv_buffer.getvalue().encode())

## Can also pass these through the request data
# BUCKET_NAME = os.environ['BUCKET_NAME'].strip()
# MODEL_DIR = os.environ['MODEL_DIR'].strip()
# UPLOAD_DIR = os.environ['UPLOAD_DIR'].strip()
# TEMP_DATA = os.environ['TEMP_DATA'].strip()
# PRED_COL = os.environ['PRED_COL'].strip() 


BUCKET_NAME = "pet-adoption-mm"
MODEL_DIR = "models/mm-binclass-model".strip("/") # in case someone includes a "/" when setting environmental variable
UPLOAD_DIR = "uploads".strip("/") 
TEMP_DATA = "tmp/mmim.csv"
PRED_COL = "AdoptionSpeed" 

response = s3.list_objects_v2(Bucket=BUCKET_NAME)


## --- Download Model --- ## 

model_files = [obj['Key'] for obj in response["Contents"] if MODEL_DIR in obj["Key"]]

for file in model_files:
  # Create any missing directories
  os.makedirs(os.path.dirname(file), exist_ok=True)
  s3.download_file(Bucket=BUCKET_NAME, Key=file, Filename=file)

predictor = MultiModalPredictor.load(MODEL_DIR)

## --- Download Newest Images --- ## 

uploads = [obj['Key'].lstrip(f"/{UPLOAD_DIR}") for obj in response["Contents"] if UPLOAD_DIR in obj["Key"]]
uploads.remove("") # created by UPLOAD_DIR itself
new_folder = max(uploads).split("/")[0]
new_images = [f"{UPLOAD_DIR}/{obj}" for obj in uploads if obj.split("/")[0] == new_folder and obj.split(".")[-1] in ("jpg","jpeg","png")]

for img in new_images:
  os.makedirs(os.path.dirname(img), exist_ok=True)
  s3.download_file(Bucket=BUCKET_NAME, Key=img, Filename=img)

## --- Download Temp Tabular Data (to DataFrame) --- ## 

object = s3.get_object(Bucket=BUCKET_NAME, Key=TEMP_DATA)
csv_data = object['Body'].read().decode('utf-8')
df = pd.read_csv(StringIO(csv_data))


# Model needs full path to image in df['Image']
df['Image'] = UPLOAD_DIR + "/" + new_folder + "/" + df['Image'] 

## --- Generate Predictions --- ## 

df[PRED_COL] = predictor.predict(df)
df['Prob'] = predictor.predict_proba(df).max(axis=1)

## --- Write to Database/S3 --- ##

# Add label for model type (image or non-image)
df['ImageModel'] = 1 # Instead of 1/0, you could give the full model name if you wanted to track version history
df.drop("Image", axis=1, inplace=True)

@app.get('/')
def my_function():
  s3_upload_df(df, "results/mmim_results.csv")
  return 

if __name__=="__main__":
  uvicorn.run(app,host="0.0.0.0",port=9000)

