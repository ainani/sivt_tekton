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

    ### - Setting Environment values
    ```sh
    export IMAGENAME="<service_installer_tekton:v141>"
    export GIT_FQDN="<Private_git_fqdn>"
    export GITUSER="<git_username>"
    export GITPAT="<git_PAT>"
    export GITREPO="<FULL PATH OF GIT REPO>"
    export GITBRANCH="<Branch to clone from. Defaults to master, if not specified>"
    ```
    
    ### - Triggering the pipeline
    ```sh
    ./launch.sh --create-cluster --exec day0 #for day0 deployment
    ```
    ```sh
    ./launch.sh --create-cluster --exec day2 --targetcluster <mgmt/all>
    #for upgrade operation
    ```
    




