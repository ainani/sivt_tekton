# ARCAS TEKTON CICD PIPELINE
Setup Kubernetes cluster

For Minikube: 
     
wget https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
chmod +x minikube-linux-amd64
sudo mv minikube-linux-amd64 /usr/local/bin/minikube
minikube version



Install kubectl 

curl -LO https://storage.googleapis.com/kubernetes-release/release/`curl -s https://storage.googleapis.com/kubernetes-release/release/stable.txt`/bin/linux/amd64/kubectl
chmod +x kubectl
sudo mv kubectl  /usr/local/bin/

Start minikube 
minikube start


Install Tekton 
kubectl apply --filename https://github.com/tektoncd/pipeline/releases/download/v0.19.0/release.notags.yaml

Install Tekton cli
wget https://github.com/tektoncd/cli/releases/download/v0.15.0/tkn_0.15.0_Linux_x86_64.tar.gz 
tar -zxvf tkn_0.15.0_Linux_x86_64.tar.gz 
cp tkn /usr/bin/; 

---

Execution: 
Target the pipeline and execute:

- kubectl apply -f setup_pipeline.yaml

- tkn pipeline start --showlog arcas-cicd 
