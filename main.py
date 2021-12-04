import boto3
import os
import time



OhioClient = boto3.client("ec2", region_name="us-east-2")
NVClient = boto3.client("ec2", region_name="us-east-1")
LBClient = boto3.client("elbv2", region_name= "us-east-1")
ASGClient = boto3.client("autoscaling", region_name="us-east-1")

PostgresUserData = """#!/bin/bash
                    sudo apt update
                    sudo apt install postgresql postgresql-contrib -y
                    sudo -u postgres psql -c "CREATE USER cloud WITH PASSWORD 'cloud';"
                    sudo -u postgres createdb -O cloud tasks
                    sudo sed -i "59 c listen_addresses='*'" /etc/postgresql/10/main/postgresql.conf
                    sudo sed -i "$ a host all all 0.0.0.0/0 trust" /etc/postgresql/10/main/pg_hba.conf
                    sudo ufw allow 5432/tcp
                    sudo systemctl restart postgresql 
                    """

DjangoUserData = """#!/bin/bash
                sudo apt update
                cd /home/ubuntu
                git clone https://github.com/lucasmuchaluat/tasks.git
                sudo sed -i 's/node1/{0}/g' /home/ubuntu/tasks/portfolio/settings.py
                cd tasks
                ./install.sh
                sudo reboot
                """


NVami = "ami-0279c3b3186e54acd"
OHami = "ami-020db2c14939a8efb"



def generateKeys(client,key_name, filename):

	keyPair = client.create_key_pair(KeyName=key_name)
	privateKey = keyPair["KeyMaterial"]

	if filename in os.listdir():
		os.remove(filename)

	with open(filename, "w") as file:
		file.write(privateKey)
		os.chmod(filename, 0o400)

	return key_name

def getInstanceIP(client, instance):

	instances = client.describe_instances(Filters = [

		{
			'Name' : 'tag:Name',
			'Values' : [instance]
		}
	])

	for i in instances["Reservations"]:

		for j in i['Instances']:
			
			if j['State']['Name'] == 'running':

				return j['PublicIpAddress']




def createInstance(client, image_id,instance_type,key_name,user_data,sg_name):

	instance = client.run_instances(

		ImageId = image_id,
		InstanceType = instance_type,
		MaxCount = 1,
		MinCount = 1,
		KeyName = key_name,
		UserData = user_data,
		SecurityGroups = [sg_name],
		TagSpecifications = [
			{
				'ResourceType' : 'instance',
				'Tags' : [
					{

						'Key' : 'Name',
						'Value' : 'CloudProject'

					}
				]
			}
		])

def createAMI(client,instance):


	instances = client.describe_instances(Filters = [

		{
			'Name' : 'tag:Name',
			'Values' : [instance]
		}
	])

	for i in instances["Reservations"]:

		for j in i['Instances']:
			
			if j['State']['Name'] == 'running':

				instance_id = j['InstanceId']


	AMI = client.create_image(

		Name = "DjangoAMI",
		InstanceId = instance_id,
		NoReboot = False,
		TagSpecifications = [

			{

				"ResourceType" : "image",
				"Tags" : [

				{
					"Key" : "Name",
					"Value" : "DjangoAMI"
				}]
			}]
		)

	return AMI['ImageId'], instance_id


def terminate(client,instance):

	instances = client.describe_instances(Filters = [

		{
			'Name' : 'tag:Name',
			'Values' : [instance]
		}
	])

	for i in instances["Reservations"]:

		for j in i['Instances']:
			
			if j['State']['Name'] == 'running':

				instance_id = j['InstanceId']


	client.terminate_instances(InstanceIds=[instance_id])

def createSG(r_name, name):

	region = boto3.resource("ec2", region_name=r_name)

	security_group = region.create_security_group(

		GroupName= name + "-security-group",
		Description = name + " Security Group",
		TagSpecifications = [
			{

				"ResourceType" : "security-group",
				"Tags" : [

					{
						'Key' : 'Name',
						'Value' : name + "-security-group"
					}


				]
			}

		]
	)

	if name == 'postgres':

		security_group.authorize_ingress(
			GroupName = name + "-security-group",
			IpPermissions = [
				{'IpProtocol' : 'tcp',
					'FromPort' : 5432,
					'ToPort' : 5432,
					'IpRanges' : [{'CidrIp' : '0.0.0.0/0'}]  
				}
			] 
		)

	elif name == 'django':

		security_group.authorize_ingress(
			GroupName = name + "-security-group",
			IpPermissions = [
				{'IpProtocol' : 'tcp',
					'FromPort' : 8080,
					'ToPort' : 8080,
					'IpRanges' : [{'CidrIp' : '0.0.0.0/0'}]    
				}
			] 
		)

	security_group.authorize_ingress(
			GroupName = name + "-security-group",
			IpPermissions = [
				{'IpProtocol' : 'tcp',
					'FromPort' : 22,
					'ToPort' : 22,
					'IpRanges' : [{'CidrIp' : '0.0.0.0/0'}]    
				}
			] 
		)

	sg_name = name + "-security-group"
	return sg_name

def createLB(client, lb_client, sg_name):

	subnets = client.describe_subnets()

	subnet_list = []
	for subnet in subnets['Subnets']:
		subnet_list.append(subnet['SubnetId'])

	id_sg = client.describe_security_groups(GroupNames=[sg_name])["SecurityGroups"][0]["GroupId"]

	load_balancer = lb_client.create_load_balancer(
		Name= "Load-Balancer",
		SecurityGroups = [id_sg],
		Subnets=subnet_list

		)

	return load_balancer


def createASG(client,asg_client,image_id,user_data,sg_name,instance_id):

	id_sg = client.describe_security_groups(GroupNames=[sg_name])["SecurityGroups"][0]["GroupId"]


	asg_client.create_launch_configuration(
		LaunchConfigurationName = "LC",
		ImageId = image_id,
		SecurityGroups = [id_sg],
		InstanceType = "t2.micro",
		UserData = user_data)



	asg_client.create_auto_scaling_group(
		AutoScalingGroupName = "ASG",
		InstanceId = instance_id,
		MinSize = 1,
		MaxSize = 4,
		DesiredCapacity = 1
		)









def setup():

	print("Iniciating Setup")
	print("==================")
	time.sleep(3)
	ohio_keypair = generateKeys(OhioClient,"ohio-keypair","ohio-keypair.pem")
	print("Key Pair for OHIO generated")
	print("==================")
	oh_sg_name = createSG("us-east-2","postgres")
	print("Security Group for NV generated")
	print("==================")
	createInstance(OhioClient,OHami,"t2.micro",ohio_keypair,PostgresUserData,oh_sg_name)
	print("Ohio Instance Created.")
	print("==================")

	print("waiting for Ohio IP")

	while getInstanceIP(OhioClient,"CloudProject") == None:
		time.sleep(2)
		print(".")

	ohio_ip = getInstanceIP(OhioClient,"CloudProject")

	print("==================")
	print("Ohio IP: ", ohio_ip)
	print("==================")

	NV_keypair = generateKeys(NVClient, "nv-keypair", "nv-keypair.pem")
	print("Key Pair for NV generated")
	print("==================")
	NV_sg_name = createSG("us-east-1", "django")
	print("Security Group for NV generated")
	print("==================")
	createInstance(NVClient, NVami, "t2.micro", NV_keypair, DjangoUserData.format(ohio_ip),NV_sg_name)
	print("North Virginia Instance Created.")
	time.sleep(300)
	print("==================")
	print("waiting for North Virginia IP")
	while getInstanceIP(NVClient,"CloudProject") == None:
		time.sleep(2)
		print(".")

	nv_ip = getInstanceIP(NVClient,"CloudProject")

	print("==================")
	print("North Virginia IP: ", nv_ip)
	print("==================")
	print("Creating AMI for North Virginia")
	AMI_id,instance_id = createAMI(NVClient,"CloudProject")
	
	createLB(NVClient, LBClient, NV_sg_name)
	createASG(NVClient, ASGClient, AMI_id,DjangoUserData,NV_sg_name,instance_id)
	time.sleep(60)
	terminate(NVClient,"CloudProject")

setup()













