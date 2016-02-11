$env:OS_AUTH_URL="https://your-server.domain.com:5000/v2.0"
$env:OS_TENANT_NAME="your-project"
$env:OS_USERNAME="your-user"
#CACERT is optional, and only use it if you don't have a CA-signed certificate for your cloud
#$env:OS_CACERT="C:\your\path\vio.pem"
$Password = Read-Host -Prompt "OpenStack User Password?" -AsSecureString
$env:OS_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($Password))