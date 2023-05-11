#### Launching EC2 instance to run Jupyter Notebook Server 
1. Create Security Group With Inbound Rules 
   - SSH -- Port Range 22 -- Anywhere IPv4 (0.0.0.0/0)
   - HTTPS -- Port Range 443 -- Anywhere IPv4 (0.0.0.0/0)
   - Custom TCP -- Port Range 8888 -- Anywhere IPv4 (0.0.0.0/0)
2. Create EC2 Instance (Amazon Linux 2023, apply security group, generate or use existing .pem key)
3. Connect to Instance via SSH 
4. python3 -m venv venv
5. Activate venv, pip install requirements (including jupyter)
6. jupyter notebook --generate-config 
7. Generate hashed password: python3 -c 'from notebook.auth import passwd; print(passwd())'
8. Copy hashed password into jupyter config file (c.NotebookApp.password = '')
9. Launch jupyter server: jupyter notebook 
   1.  If you have trouble connecting, you can specify jupyter notebook --ip 0.0.0.0 --port=8888
   2.  I'm not sure why this would be needed given the security group but whatever...
10. Connect to jupyter server: `http://<instance_public_ip>:8888/`
    1.  If you used --ip and --port, paste token from ssh shell
11. Log into server using unhashed password


#### Configuring EC22 instance for AutoML Project


###### Copy data from local: scp -i automl-mm2.pem -r sagemaker-automm ec2-user@ec2-18-188-233-157.us-east-2.compute.amazonaws.com:~/sagemaker-automm
###### - Don't do this -- upload is always slower than download 

1. Download zip from kaggle to local (or in instance  via API if it works -- skip step 2).

2. Upload zip to s3 bucket 

3. Add aws credentials to ec2 instance

4. Copy zip file from s3 bucket via cli: `aws s3 cp s3://<bucket_name>/<object_name>`

5. Unzip file to data directory  

### Issues 

- Connection issues (had to specify 0.0.0.0 in ip flag)
- Jupyter server crashing in t3.large instance 
  - m4.xlarge crashiung 
  - moving up to m4.4xlarge with 64GB ram and 50GB storage 
    - connection issues -- didn't change anything?? too expensive, switching back  m4.xlarge when i'm back on instance
- Now it just keeps crashing locally.......
- In instance again, but at 120 seconds saying no checkpoints were generated. 

```bash
ValueError: Resuming checkpoint '/home/ec2-user/AutogluonModels/ag-20230418_194439/last.ckpt' and final checkpoint '/home/ec2-user/AutogluonModels/ag-20230418_194439/model.ckpt' both don't exist. Consider starting training from scratch
```
And if I run it longer, it crashes the instance -- reducing time and to medium quality

- Trying 6000 seconds, medium_quality, reduced sample (800 train, 200 test)
  - Crash again! Did achieve a checkpoint where I got 72% roc_auc (in training) in binary classification. Resume training with: 
    - predictor = MultiModalPredictor.load("<path/to/interrupted/model/>", resume=True)
    - predictor.fit(train_data)
  - --> 83% roc_auc training after another 10 minutes of training 
- Test performance still terrible! {'roc_auc': 0.5962393162393163}


Not going to try and improve yet -- will save model and work on filling out rest of the pipeline.
