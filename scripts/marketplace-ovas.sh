#!/usr/bin/env bash
set -e

export CLOUD_CSP_REFRESH_TOKEN="$(cat ~/.ssh/csp_api_token)"
export CLOUD_CSP_ACCESS_TOKEN="https://console.cloud.vmware.com/csp/gateway/am/api/auth/api-tokens/authorize?refresh_token=${CLOUD_CSP_REFRESH_TOKEN}"
export MARKETPLACE_TKG_LATEST_PRODUCTID="e2b7b5f7-07e3-4fb2-baeb-b46209c4aa3c"
export MARKETPLACE_TKG_LATEST_PRODUCTID_URL="https://gtwstg.market.csp.vmware.com/api/v1/products/${MARKETPLACE_TKG_LATEST_PRODUCTID}"
export MARKETPLACE_TKG_LATEST_PRODUCTID_DOWNLOAD_URL="https://gtwstg.market.csp.vmware.com/api/v1/products/${MARKETPLACE_TKG_LATEST_PRODUCTID}/download"
export MARKETPLACE_AVICONTROLLER_LATEST_PRODUCTID="25dbebae-3721-46cc-844d-fa9e3528902c"
export MARKETPLACE_AVICONTROLLER_LATEST_PRODUCTID_URL="https://gtwstg.market.csp.vmware.com/api/v1/products/${MARKETPLACE_AVICONTROLLER_LATEST_PRODUCTID}"
export MARKETPLACE_AVICONTROLLER_LATEST_PRODUCTID_DOWNLOAD_URL="https://gtwstg.market.csp.vmware.com/api/v1/products/${MARKETPLACE_AVICONTROLLER_LATEST_PRODUCTID}/download"
function get_photon_latest_version_ova() {
        local token=$(curl --location --request POST $CLOUD_CSP_ACCESS_TOKEN | sed -n 's|.*"access_token":"\([^"]*\)".*|\1|p')
        if [ -z "$token" ]; then 
              echo 'cannot exchange refresh token for access token'
              exit 1
        else
             $(curl -X GET $MARKETPLACE_TKG_LATEST_PRODUCTID_URL \
                --header "accept: application/json" \
              	--header "csp-auth-token: $token" \
                --header "Content-Type: application/json" \
                -o productDetails.json
                )
              local LATEST_VERSION=$( jq -r '.response.data.latestversion' productDetails.json)
              local FILEID=$(jq -r --arg LATEST_VERSION "$LATEST_VERSION" '.response.data.productdeploymentfilesList[] | select(.appversion == $LATEST_VERSION) | .fileid' productDetails.json)
                
                if [ -z "$FILEID" ]; then
                    echo 'cannot find ova file id for download'
                    exit 2
               
                else 
                    local PRESIGN_URL=$(curl -X POST $MARKETPLACE_TKG_LATEST_PRODUCTID_DOWNLOAD_URL \
                    --header "accept: application/json" \
                    --header "csp-auth-token: $token" \
                    --header "Content-Type: application/json" \
                    --data-raw "{\"eulaAccepted\":true,\"deploymentFileId\":\"${FILEID}\"}" | sed -n 's|.*"presignedurl":"\([^"]*\)".*|\1|p')
                    
                    if [ -z "$PRESIGN_URL" ]; then
                        echo 'cannot find ova download url'
                        exit 3
                    else
                      wget -O photon-3-kube-v1-$LATEST_VERSION.ova $PRESIGN_URL
                    fi
                fi
              
        fi
 
}
function get_avicontroller_latest_version_ova() {
        local token=$(curl --location --request POST $CLOUD_CSP_ACCESS_TOKEN | sed -n 's|.*"access_token":"\([^"]*\)".*|\1|p')
        if [ -z "$token" ]; then 
              echo 'cannot exchange refresh token for access token'
              exit 1
        else
             $(curl -X GET $MARKETPLACE_AVICONTROLLER_LATEST_PRODUCTID_URL \
                --header "accept: application/json" \
              	--header "csp-auth-token: $token" \
                --header "Content-Type: application/json" \
                -o productDetails.json
                )
              local LATEST_VERSION=$( jq -r '.response.data.latestversion' productDetails.json)
              local FILEID=$(jq -r --arg LATEST_VERSION "$LATEST_VERSION" '.response.data.productdeploymentfilesList[] | select(.appversion == $LATEST_VERSION) | .fileid' productDetails.json)
                
                if [ -z "$FILEID" ]; then
                    echo 'cannot find avi controller ova file id for download'
                    exit 2
               
                else 
                    local PRESIGN_URL=$(curl -X POST $MARKETPLACE_AVICONTROLLER_LATEST_PRODUCTID_DOWNLOAD_URL \
                    --header "accept: application/json" \
                    --header "csp-auth-token: $token" \
                    --header "Content-Type: application/json" \
                    --data-raw "{\"eulaAccepted\":true,\"deploymentFileId\":\"${FILEID}\"}" | sed -n 's|.*"presignedurl":"\([^"]*\)".*|\1|p')
                    
                    if [ -z "$PRESIGN_URL" ]; then
                        echo 'cannot find avi controller ova download url'
                        exit 3
                    else
                      wget -O avi-controller-$LATEST_VERSION.ova $PRESIGN_URL
                    fi
                fi
              
        fi
 
}

main() {
  get_avicontroller_latest_version_ova
  get_photon_latest_version_ova
}

main

 
