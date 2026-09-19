import os
from locust import HttpUser,task,between

class DispatcherUser(HttpUser):
    wait_time=between(.2,1)
    def on_start(self):
        response=self.client.post('/api/v1/auth/login',json={'username':'dispatcher','password':os.environ['DEMO_PASSWORD']})
        if response.status_code!=200:
            raise RuntimeError('Не удалось войти')
        self.client.headers['Authorization']='Bearer '+response.json()['access_token']
    @task(4)
    def dashboard(self):
        self.client.get('/api/v1/predictions?latest=true')
    @task(2)
    def events(self):
        self.client.get('/api/v1/events?limit=50')
    @task
    def objects(self):
        self.client.get('/api/v1/objects')
