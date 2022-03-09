import os
from util import cmd_runner
import json
import yaml
from util.cmd_helper import CmdHelper
import socket
import struct

def file_linker(specfile, configfile):
    with open(specfile) as f:
        jsonspec = json.load(f)

    with open(configfile) as f1:
        yamlinput = yaml.safe_load(f1)

    yamlinput['vsphere']['server'] = jsonspec['envSpec']['vcenterDetails']['vcenterAddress']
    yamlinput['vsphere']['username'] = jsonspec['envSpec']['vcenterDetails']['vcenterSsoUser']
    yamlinput['vsphere']['password'] = \
        jsonspec['envSpec']['vcenterDetails']['vcenterSsoPasswordBase64']
    server = jsonspec['envSpec']['vcenterDetails']['vcenterAddress']
    rcmd = cmd_runner.RunCmd()
    tlscmd = "echo -n | openssl s_client -connect {}:443 2>/dev/null | " \
             "openssl x509 -noout -fingerprint -sha1".format(server)
    tlstb = str(rcmd.run_cmd_output(tlscmd)).lstrip('sha1 Fingerprint=').rstrip('\n')
    yamlinput['vsphere']['tlsThumbprint'] = tlstb
    yamlinput['tkg']['common']['nodeOva'] = \
        jsonspec['envSpec']['customRepositorySpec']['tkgCustomImageRepository']
    yamlinput['tkg']['common']['dnsServers'][0] = \
        jsonspec['envSpec']['infraComponents']['dnsServersIp']
    yamlinput['tkg']['common']['ntpServers'][0] = \
        jsonspec['envSpec']['infraComponents']['ntpServers']
    yamlinput['tkg']['management']['cluster']['name'] =\
        jsonspec['tkgComponentSpec']['tkgMgmtComponents']['tkgMgmtClusterName']
    yamlinput['tkg']['management']['cluster']['plan'] =\
        jsonspec['tkgComponentSpec']['tkgMgmtComponents']['tkgMgmtDeploymentType']
    yamlinput['tkg']['management']['cluster']['size'] =\
        jsonspec['tkgComponentSpec']['tkgMgmtComponents']['tkgMgmtSize']
    dcname = jsonspec['envSpec']['vcenterDetails']['vcenterDatacenter']
    dsname = jsonspec['envSpec']['vcenterDetails']['vcenterDatastore']
    mgmt_network = jsonspec['tkgComponentSpec']['tkgMgmtComponents']['tkgMgmtNetworkName']
    resource_pool = jsonspec['envSpec']['vcenterDetails']['resourcePoolName']
    disksize = jsonspec['tkgComponentSpec']['tkgMgmtComponents']['tkgMgmtStorageSize']
    memsize = jsonspec['tkgComponentSpec']['tkgMgmtComponents']['tkgMgmtMemorySize']
    cpus = jsonspec['tkgComponentSpec']['tkgMgmtComponents']['tkgMgmtCpuSize']
    yamlinput['tkg']['management']['deployment']['datacenter'] = dcname
    yamlinput['tkg']['management']['deployment']['datastore'] = dsname
    foldername = "TEKTON"
    vcpass_base64 = jsonspec['envSpec']['vcenterDetails']['vcenterSsoPasswordBase64']
    vcpass = CmdHelper.decode_base64(vcpass_base64)
    format_vcpass = ''.join(vcpass)
    os.putenv("GOVC_URL", server)
    os.putenv("GOVC_USERNAME", jsonspec['envSpec']['vcenterDetails']['vcenterSsoUser'])
    os.putenv("GOVC_PASSWORD", format_vcpass)
    os.putenv("GOVC_INSECURE", str("true"))
    govc_check_folder_cmd = "govc folder.info /{dc}/vm/{foldername}}".\
        format(dc=dcname, foldername=foldername)
    folder_info = rcmd.run_cmd_output(govc_check_folder_cmd)
    if 'not found' in folder_info:
        govc_cmd = "govc folder.create /{dc}/vm/{foldername}".format(dc=dcname, foldername=foldername)
        rcmd.run_cmd_only(cmd=govc_cmd)

    yamlinput['tkg']['management']['deployment']['folder'] = foldername
    yamlinput['tkg']['management']['deployment']['network'] = mgmt_network
    yamlinput['tkg']['management']['deployment']['resourcePool'] = resource_pool
    yamlinput['tkg']['management']['controlPlane']['diskGib'] = disksize
    yamlinput['tkg']['management']['controlPlane']['memoryMib'] = memsize
    yamlinput['tkg']['management']['controlPlane']['cpus'] = cpus

    yamlinput['tkg']['management']['worker']['diskGib'] = disksize
    yamlinput['tkg']['management']['worker']['memoryMib'] = memsize
    yamlinput['tkg']['management']['worker']['cpus'] = cpus

    yamlinput['tkg']['management']['segment']['gatewayCidr'] = \
        jsonspec['tkgMgmtDataNetwork']['tkgMgmtDataNetworkGatewayCidr']
    yamlinput['tkg']['management']['segment']['dhcpStart'] = \
        jsonspec['tkgMgmtDataNetwork']['tkgMgmtAviServiceIpStartRange']
    yamlinput['tkg']['management']['segment']['dhcpEnd'] = \
        jsonspec['tkgMgmtDataNetwork']['tkgMgmtAviServiceIpEndRange']

    yamlinput['tkg']['management']['dataVipSegment']['gatewayCidr'] = \
        jsonspec['tkgMgmtDataNetwork']['tkgMgmtDataNetworkGatewayCidr']
    yamlinput['tkg']['management']['dataVipSegment']['dhcpStart'] = \
        jsonspec['tkgMgmtDataNetwork']['tkgMgmtAviServiceIpStartRange']
    yamlinput['tkg']['management']['dataVipSegment']['dhcpEnd'] = \
        jsonspec['tkgMgmtDataNetwork']['tkgMgmtAviServiceIpEndRange']
    yamlinput['tkg']['management']['dataVipSegment']['staticIpStart'] = \
        jsonspec['tkgMgmtDataNetwork']['tkgMgmtAviServiceIpStartRange']
    yamlinput['tkg']['management']['dataVipSegment']['staticIpEnd'] = \
        jsonspec['tkgMgmtDataNetwork']['tkgMgmtAviServiceIpEndRange']

    # clusterVipSegment
    yamlinput['tkg']['management']['clusterVipSegment']['gatewayCidr'] = \
     jsonspec['tkgComponentSpec']['tkgClusterVipNetwork']['tkgClusterVipNetworkGatewayCidr']
    yamlinput['tkg']['management']['clusterVipSegment']['dhcpStart'] = \
        jsonspec['tkgComponentSpec']['tkgClusterVipNetwork']['tkgClusterVipIpStartRange']
    yamlinput['tkg']['management']['clusterVipSegment']['dhcpEnd'] = \
        jsonspec['tkgComponentSpec']['tkgClusterVipNetwork']['tkgClusterVipIpEndRange']
    yamlinput['tkg']['management']['clusterVipSegment']['staticIpStart'] = \
        jsonspec['tkgComponentSpec']['tkgClusterVipNetwork']['tkgClusterVipIpStartRange']
    yamlinput['tkg']['management']['clusterVipSegment']['staticIpEnd'] = \
        jsonspec['tkgComponentSpec']['tkgClusterVipNetwork']['tkgClusterVipIpEndRange']

    # sharedservices
    yamlinput['tkg']['sharedService']['cluster']['name'] =\
        jsonspec['tkgComponentSpec']['tkgMgmtComponents']['tkgSharedserviceClusterName']
    yamlinput['tkg']['sharedService']['cluster']['plan'] =\
        jsonspec['tkgComponentSpec']['tkgMgmtComponents']['tkgSharedserviceDeploymentType']
    yamlinput['tkg']['sharedService']['cluster']['size'] =\
        jsonspec['tkgComponentSpec']['tkgMgmtComponents']['tkgSharedserviceSize']

    sdisksize = jsonspec['tkgComponentSpec']['tkgMgmtComponents']['tkgSharedserviceStorageSize']
    smemsize = jsonspec['tkgComponentSpec']['tkgMgmtComponents']['tkgSharedserviceMemorySize']
    scpus = jsonspec['tkgComponentSpec']['tkgMgmtComponents']['tkgSharedserviceCpuSize']

    yamlinput['tkg']['sharedService']['deployment']['datacenter'] = dcname
    yamlinput['tkg']['sharedService']['deployment']['datastore'] = dsname
    yamlinput['tkg']['sharedService']['deployment']['folder'] = foldername
    yamlinput['tkg']['sharedService']['deployment']['network'] = mgmt_network
    yamlinput['tkg']['sharedService']['deployment']['resourcePool'] = resource_pool
    # yamlinput['tkg']['sharedService']['controlPlane']['endpoint'] = \
    #    jsonspec['tkgMgmtDataNetwork']['tkgMgmtDataNetworkGatewayCidr']
    #    jsonspec['tkgMgmtDataNetwork']['tkgMgmtDataNetworkGatewayCidr']
    yamlinput['tkg']['sharedService']['controlPlane']['diskGib'] = sdisksize
    yamlinput['tkg']['sharedService']['controlPlane']['memoryMib'] = smemsize
    yamlinput['tkg']['sharedService']['controlPlane']['cpus'] = scpus
    yamlinput['tkg']['sharedService']['worker']['diskGib'] = sdisksize
    yamlinput['tkg']['sharedService']['worker']['memoryMib'] = smemsize
    yamlinput['tkg']['sharedService']['worker']['cpus'] = scpus
    yamlinput['tkg']['sharedService']['segment']['gatewayCidr'] = \
        jsonspec['tkgMgmtDataNetwork']['tkgMgmtDataNetworkGatewayCidr']
    yamlinput['tkg']['sharedService']['segment']['dhcpStart'] = \
        jsonspec['tkgMgmtDataNetwork']['tkgMgmtAviServiceIpStartRange']
    yamlinput['tkg']['sharedService']['segment']['dhcpEnd'] =\
        jsonspec['tkgMgmtDataNetwork']['tkgMgmtAviServiceIpEndRange']
    yamlinput['tkg']['sharedService']['extensions_spec']['harbor']['adminPassword'] = \
        jsonspec['harborSpec']['harborPasswordBase64']
    yamlinput['tkg']['sharedService']['extensions_spec']['harbor']['hostname'] = \
        jsonspec['harborSpec']['harborFqdn']

    # workloadClusters:

    wdisksize = jsonspec['tkgWorkloadComponents']['tkgWorkloadStorageSize']
    wmemsize = jsonspec['tkgWorkloadComponents']['tkgWorkloadMemorySize']
    wcpus = jsonspec['tkgWorkloadComponents']['tkgWorkloadCpuSize']

    yamlinput['tkg']['workloadClusters'][0]['cluster']['name'] = \
        jsonspec['tkgWorkloadComponents']['tkgWorkloadClusterName']
    yamlinput['tkg']['workloadClusters'][0]['cluster']['plan'] = \
        jsonspec['tkgWorkloadComponents']['tkWorkloadDeploymentType']
    yamlinput['tkg']['workloadClusters'][0]['cluster']['size'] = \
        jsonspec['tkgWorkloadComponents']['tkgWorkloadSize']
    yamlinput['tkg']['workloadClusters'][0]['deployment']['datacenter'] = dcname
    yamlinput['tkg']['workloadClusters'][0]['deployment']['datastore'] = dsname
    yamlinput['tkg']['workloadClusters'][0]['deployment']['folder'] = foldername
    yamlinput['tkg']['workloadClusters'][0]['deployment']['network'] = \
        jsonspec['tkgWorkloadComponents']['tkgWorkloaNetworkName']
    yamlinput['tkg']['workloadClusters'][0]['deployment']['resourcePool'] = resource_pool
    # yamlinput['tkg']['workloadClusters'][0]['controlPlane']['endpoint'] = \
    #    jsonspec['tkgWorkloadDataNetwork']['tkgWorkloadDataNetworkGatewayCidr']
    yamlinput['tkg']['workloadClusters'][0]['controlPlane']['diskGib'] = wdisksize
    yamlinput['tkg']['workloadClusters'][0]['controlPlane']['memoryMib'] = wmemsize
    yamlinput['tkg']['workloadClusters'][0]['controlPlane']['cpus'] = wcpus
    # worker
    yamlinput['tkg']['workloadClusters'][0]['worker']['diskGib'] = wdisksize
    yamlinput['tkg']['workloadClusters'][0]['worker']['memoryMib'] = wmemsize
    yamlinput['tkg']['workloadClusters'][0]['worker']['cpus'] = wcpus
    # segment
    yamlinput['tkg']['workloadClusters'][0]['segment']['gatewayCidr'] = \
        jsonspec['tkgWorkloadDataNetwork']['tkgWorkloadDataNetworkGatewayCidr']
    yamlinput['tkg']['workloadClusters'][0]['segment']['dhcpStart'] = \
        jsonspec['tkgWorkloadDataNetwork']['tkgWorkloadAviServiceIpStartRange']
    yamlinput['tkg']['workloadClusters'][0]['segment']['dhcpEnd'] = \
        jsonspec['tkgWorkloadDataNetwork']['tkgWorkloadAviServiceIpEndRange']
    # datavip
    yamlinput['tkg']['workloadClusters'][0]['dataVipSegment']['gatewayCidr'] = \
        jsonspec['tkgWorkloadDataNetwork']['tkgWorkloadDataNetworkGatewayCidr']
    yamlinput['tkg']['workloadClusters'][0]['dataVipSegment']['dhcpStart'] = \
        jsonspec['tkgWorkloadDataNetwork']['tkgWorkloadAviServiceIpStartRange']
    yamlinput['tkg']['workloadClusters'][0]['dataVipSegment']['dhcpEnd'] = \
        jsonspec['tkgWorkloadDataNetwork']['tkgWorkloadAviServiceIpEndRange']
    # grafana

    yamlinput['tkg']['workloadClusters'][0]['extensionsSpec']['grafana']['adminPassword'] = \
        jsonspec['tanzuExtensions']['monitoring']['grafanaPasswordBase64']

    yamlinput['integrations']['api_token'] = \
        jsonspec['envSpec']['saasEndpoints']['tmcDetails']['tmcRefreshToken']

    yamlinput['integrations']['api_token'] = \
        jsonspec['envSpec']['saasEndpoints']['tmcDetails']['tmcRefreshToken']

    # avi
    # yamlinput['avi']['ovaPath'] = jsonspec['saasEndpoints']['tmcDetails']['tmcRefreshToken']
    yamlinput['avi']['password'] = jsonspec['tkgComponentSpec']['aviComponents']['aviPasswordBase64']
    yamlinput['avi']['deployment']['datacenter'] = dcname
    yamlinput['avi']['deployment']['datastore'] = dsname
    yamlinput['avi']['deployment']['folder'] = foldername
    yamlinput['avi']['deployment']['network'] = \
        jsonspec['tkgComponentSpec']['aviMgmtNetwork']['aviMgmtNetworkName']
    yamlinput['avi']['deployment']['resourcePool'] = resource_pool
    yamlinput['avi']['deployment']['parameters']['gateway'] = \
        jsonspec['tkgComponentSpec']['aviMgmtNetwork']['aviMgmtNetworkGatewayCidr']
    yamlinput['avi']['deployment']['parameters']['ip'] = \
        jsonspec['tkgComponentSpec']['aviComponents']['aviClusterIp']
    gw_cidr = jsonspec['tkgComponentSpec']['aviMgmtNetwork']['aviMgmtNetworkGatewayCidr']

    netmask_bit = gw_cidr.split('/')[1]
    host_bits = 32 - int(netmask_bit)
    netmask = socket.inet_ntoa(struct.pack('!I', (1 << 32) - (1 << host_bits)))
    yamlinput['avi']['deployment']['parameters']['netmask'] = netmask

    # segment
    yamlinput['avi']['segment']['gatewayCidr'] = \
        jsonspec['tkgComponentSpec']['aviMgmtNetwork']['aviMgmtNetworkGatewayCidr']
    yamlinput['avi']['segment']['dhcpStart'] = \
        jsonspec['tkgComponentSpec']['aviMgmtNetwork']['aviMgmtServiceIpStartrange']
    yamlinput['avi']['segment']['dhcpEnd'] = \
        jsonspec['tkgComponentSpec']['aviMgmtNetwork']['aviMgmtServiceIpEndrange']
    # segment
    # yamlinput['avi']['conf']['dns'] = jsonspec['envSpec']['infraComponents']['dnsServersIp']
    # yamlinput['avi']['conf']['ntp'] = jsonspec['envSpec']['infraComponents']['ntpServers']
    avi_dns_server = jsonspec['envSpec']['infraComponents']['dnsServersIp']
    avi_ntp_server = jsonspec['envSpec']['infraComponents']['ntpServers']
    yamlinput['avi']['conf']['backup']['passphrase'] = \
        jsonspec['tkgComponentSpec']['aviComponents']['aviBackupPassphraseBase64']
    yamlinput['avi']['conf']['backup']['commonName'] = \
        jsonspec['tkgComponentSpec']['aviComponents']['aviController01Fqdn']
    yamlinput['avi']['conf']['cert']['commonName'] = \
        jsonspec['tkgComponentSpec']['aviComponents']['aviController01Fqdn']
    yamlinput['avi']['cloud']['dc'] = dcname
    yamlinput['avi']['cloud']['network'] = \
        jsonspec['tkgComponentSpec']['aviMgmtNetwork']['aviMgmtNetworkName']
    yamlinput['avi']['cloud']['ipamProfileName'] = \
        jsonspec['tkgComponentSpec']['aviMgmtNetwork']['aviMgmtNetworkName']
    yamlinput['avi']['dataNetwork']['name'] = \
        jsonspec['tkgComponentSpec']['tkgClusterVipNetwork']['tkgClusterVipNetworkName']
    preformat_cidr = \
        jsonspec['tkgComponentSpec']['tkgClusterVipNetwork']['tkgClusterVipNetworkGatewayCidr']
    address_bit = preformat_cidr.split('/')[0]
    netmask_bit = preformat_cidr.split('/')[1]
    octect_replace = address_bit.split('.')
    octect_replace[3] = '0'
    octect_join = '.'.join(octect_replace)
    formatted_cidr = octect_join + '/' + netmask_bit
    yamlinput['avi']['dataNetwork']['cidr'] = formatted_cidr
    startrange = jsonspec['tkgComponentSpec']['tkgClusterVipNetwork']['tkgClusterVipIpStartRange']
    endrange = jsonspec['tkgComponentSpec']['tkgClusterVipNetwork']['tkgClusterVipIpEndRange']
    iprange = str(startrange) + " - " + str(endrange)
    yamlinput['avi']['dataNetwork']['staticRange'] = iprange
    with open(configfile, 'w') as stream:
        try:
            yaml.dump(yamlinput, stream, default_flow_style=False)
        except yaml.YAMLError as exc:
            print(exc)
    with open(configfile) as f:
        r_string = '[' + avi_dns_server + ']'
        replace_string = f.read().replace('avidnsserver', r_string)
    with open(configfile, 'w') as f:
        f.write(replace_string)
    with open(configfile) as f:
        r_string = '[' + avi_ntp_server + ']'
        replace_string = f.read().replace('avintpserver', r_string)
    with open(configfile, 'w') as f:
        f.write(replace_string)
