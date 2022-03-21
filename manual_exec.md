``` sh
#MANUAL INPUTS FROM THE USER TO BE EXPORTED 
export IMAGENAME="10.202.233.205:80/library/service_installer_tekton:v141"
export GIT_FQDN=gitlab.eng.vmware.com
export GITUSER=smuthukumar
export GITPAT=xxxxxxxxx
export GITREPO="https://gitlab.eng.vmware.com/smuthukumar/arcas-tekton-cicd"
export GITBRANCH=alpha



# FULL e2e script

#SCRIPT
# replace for service bot creation
sed -i 's/GIT_FQDN/'"$GIT_FQDN"'/' resources/secret.yaml
sed -i 's/GITUSER/'"$GITUSER"'/' resources/secret.yaml
sed -i 's/GITPAT/'"$GITPAT"'/' resources/secret.yaml

#SCRIPT
# apply workspace resources
kubectl apply -f resources/secret.yaml -f resources/sa.yaml -f resources/day0-res.yml -f resources/day2-res.yml

#SCRIPT
# apply tasks and pipelines
kubectl apply -f tasks/git-pvtclone.yml -f tasks/avi_setup.yml  -f tasks/mgmt_setup.yml -f tasks/shared_cluster_setup.yml -f tasks/wld_setup.yml
kubectl apply -f pipelines/day0-pipeline.yml -f pipelines/upgrade-pipeline.yml
```
``` sh
#SCRIPT/MANUAL
#ACTUAL TRIGGER
#Day0
tkn p start day0-pipeline -s git-bot -w name=pipeline-shared-data,claimName=tekton-day0 -p imagename=$IMAGENAME -p giturl=$GITREPO -p branch=$GITBRANCH --showlog

# SCRIPT TO ENCOMPASS THE ABOVE COMMAND 
#  ./launch.sh --create-cluster --exec day0 #to create cluster
#  ./launch.sh  --exec day0   # to use existing cluster 

```

```sh
#Day2
#tkn p start upgrade-pipeline -s git-bot -w name=pipeline-shared-data,claimName=tekton-day0 -p imagename=$IMAGENAME -p giturl=$giturl --showlog

tkn p start upgrade-pipeline -s git-bot -w name=pipeline-shared-data,claimName=tekton-day0 -p imagename=$IMAGENAME -p giturl=$GITREPO -p branch=$GITBRANCH -p targetcluster="mgmt" --showlog
tkn p start upgrade-pipeline -s git-bot -w name=pipeline-shared-data,claimName=tekton-day0 -p imagename=$IMAGENAME -p giturl=$GITREPO -p branch=$GITBRANCH -p targetcluster="all" --showlog

#if script:
#  ./launch.sh --create-cluster --exec day2 --targetcluster <mgmt/all>
#  ./launch.sh --exec day2 --targetcluster <mgmt/all>
```

