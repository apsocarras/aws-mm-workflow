# fastapi-aws-lambda-deployment
Deploy models as FastAPI applications in AWS Lambda using Docker and Elastic Container Repository 
* Main advantage: circumvent maximum-dependency size limitations in Lambda (250 MB) while retaining a serverless architecture

These instructions build off this [youtube tutorial](https://www.youtube.com/watch?v=VYk3lwZbHBU)

---

### Preparing the Docker image
1. Train Model 
2. Save (e.g. pickle)
3. Use in FastAPI application
- to run API locally, ```python3 app.py``` and go to link and add "/docs" to URL 
- to kill process on port: ```kill $(lsof -t -i:9000)```
4. Create requirements.txt, models directory, and Dockerfile which copies these to the container.

### Uploading 
1. Create IAM User for Lambda (lambda_user) with access keys
2. Attach permissions: AmazonEC2ContainerRegistryFullAccess, AWSLambda_FullAccess, and IAMFullAccess
3. Download login .csv
4. In private window, log into the new IAM user via the login url, username, and password from the .csv 
5.  Create new ECR repository
6.  Add credentials for IAM User to your local machine via ```aws configure```

To copy the following push commands for your own repository, click "View Push Commands" in the console from the repositories page: 

![view-push-commands](img/../../img/ecr-view-push-commands.png)

7.  Retrieve an authentication token and authenticate your Docker client to your registry: ```aws ecr get-login-password --region <region-id> | docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region-id>.amazonaws.com```
 - **NOTE:** You may get a permissions denied error when you run this login command saying you can't connect to the docker daemon. Do *not* run it again with ```sudo```. When you ran ```aws configure```, you configured the credentials for the current local user, *not for the super user*. If you run the login command with ```sudo```, you will get ```Unable to locate credentials. You can configure credentials by running "aws configure". Error: Cannot perform an interactive login from a non TTY device```.
 - Instead, run ```sudo chmod 666 /var/run/docker.sock``` to give your local user permission to connect to the docker daemon before logging in ([source](https://stackoverflow.com/questions/62701131/unable-to-authenticate-my-aws-credentials-for-ecr))
8.  Build Docker image: ```docker build -t lambda-container-tutorial .```
9.  Tag your image with "latest": ```docker tag lambda-container-tutorial:latest <account-id>.dkr.ecr.<region-id>.amazonaws.com/lambda-container-tutorial:latest```
  * This saves it as the latest version of the image in your ECR repository
10.  Push container to AWS repository: ```docker push <account-id>.dkr.ecr.<region-id>.amazonaws.com/lambda-container-tutorial:latest```


### Creating the Lambda function
1. Lambda > Create Function > Container image > Select image from "Browse Images"
2. Edit timeout and memory allocation under Configuration tab on function page 
3. Create a function url > Authentication Type=NONE > Configure cross-origin resource sharing
4. Test function > template=apigateway-aws-proxy > adjust template: 
  - "path":"/"
  - "httpMethod":"GET" (according to your use case)
  - "proxy":"/"
5. Save test and test function
6. Go to function URL > add "/docs" to end of URL