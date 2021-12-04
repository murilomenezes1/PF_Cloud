import requests
import datetime



method = input("Select method: ")


if method == "GET":

	url = input("url: ")

	response = requests.get(url)
	print(response)


elif method == "POST":

	url = input("url: ")
	task = input("task: ")
	description = input("description: ")

	response = requests.post(
		url,
		data = {

			"task":task,
			"date":datetime.datetime.now(),
			"description":description
		}
	)







