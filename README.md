# TEKTON PIPELINE 

Tekton is a cloud-native solution for building CI/CD systems. It consists of Tekton Pipelines, which provides the DayO deployment and Day2 operations of TKGM 1.4.x on vSphere backed environment. 

## Features

- Bring based on Reference Architecture of TKGM on vSphere.
- E2E deployement and configuration of AVI Controller, Management, SharedServices, Workload clusters 
- Support for Day2 of upgrade from 1.4.0 to 1.4.1


## Pre-requisites

Tekton pipelines execution require the following: 

- Service Installer OVA
- Kind:Node image present locally on service installer
- Docker:dind image present locally on service installer
- Service Installer Docker image
- Private git repo

## Execution

1. Update config/deployment.json based on the environment. 
2. Traverse to path in Service Installer which has the git repo cloned.

    ### 2.a Update entries in values.yaml
    ```cat values.yaml
        #@data/values-schema
        ---
        git:
        host: <FQDN/IP OF GIT>
        repository: <GITUSER/GITREPO> #foo/master
        branch: <BRANCH>
        username: <USER WITH GIT ACCESS FOR THE REPO> #foo
        password: <GIT PAT>
        imagename: <IMAGE PATH OF SERVICE INSTALLER> #service_installer_tekton:v141 #registry:/library/service_installer_tekton:v141
    ```
    ### 2.b For triggering Day0 bringup
    ``` 
        #For launching Day0 bringup of TKGM
        ./launch.sh --create-cluster --deploy-dashboard -exec day0
    ```
    ### 2.c For triggering Day2 operation targetting management cluster
    ``` 
        #For launching Day2 upgrade opearations for Management cluster
        ./launch.sh --create-cluster --deploy-dashboard -exec day2 --targetcluster mgmt
    ```
    ### 2.d For triggering Day2 operation targetting all clusters
    ``` 
        #For launching Day2 upgrade opearations for Management cluster
        ./launch.sh --create-cluster --deploy-dashboard -exec day2 --targetcluster all
    ```
    


