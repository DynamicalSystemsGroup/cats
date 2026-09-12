# Installation:
This is a walk through on how to install dependencies for CATs on Ubuntu 20.04 LTS.

### Ubuntu 20.04 Dependencies
  ```bash
  mkdir ~/install
  cd install
  sudo apt update
  sudo apt upgrade
  sudo apt install wget build-essential ca-certificates
  sudo apt install libncurses5-dev libgdbm-dev libnss3-dev libssl-dev libreadline-dev libffi-dev
  sudo apt-get update
  sudo apt-get upgrade
  sudo apt-get install curl dpkg apt-transport-https gnupg software-properties-common git zlib1g-dev
  ```
  
### [Docker:](https://www.digitalocean.com/community/tutorials/how-to-install-and-use-docker-on-ubuntu-20-04)
  * **Installation:**
    ```bash
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
    sudo add-apt-repository "deb [arch=$(dpkg --print-architecture)] https://download.docker.com/linux/ubuntu focal stable"
    apt-cache policy docker-ce
    sudo apt install docker-ce
    docker --version
    ```
  * [**Manage Docker as a non-root user:**](https://docs.docker.com/engine/install/linux-postinstall/#manage-docker-as-a-non-root-user)
    ```bash
    sudo usermod -aG docker ${USER}
    echo <user password> | su - ${USER}
    groups
    sudo usermod -aG docker <username>
    ```

### [kubectl:](https://kubernetes.io/docs/tasks/tools/)
  ```bash
  curl -LO https://storage.googleapis.com/kubernetes-release/release/`curl -s https://storage.googleapis.com/kubernetes-release/release/stable.txt`/bin/linux/amd64/kubectl
  chmod +x ./kubectl
  sudo cp ./kubectl /usr/local/bin/kubectl
  kubectl version -o json
  ```
  * **Set `KUBE_CONFIG_PATH`:**
  ```bash
  echo 'export KUBE_CONFIG_PATH=~/.kube/config' >> ~/.profile
  source ~/.profile
  ```

### [AWS Account:](https://aws.amazon.com/)
* [**Instructions**](https://aws.amazon.com/premiumsupport/knowledge-center/create-and-activate-aws-account/)

### [AWS S3](https://aws.amazon.com/s3/)
* Generate [**Credentials**](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_access-keys.html)
   * [**Create AWS IAM Users & Access Keys**](https://aws.amazon.com/premiumsupport/knowledge-center/create-access-key/)
   * **Export AWS Access Keys to Bash Profile:**
      ```bash
      echo 'export AWS_ACCESS_KEY_ID=<AWS_ACCESS_KEY_ID>' >> ~/.profile
      echo 'export AWS_SECRET_ACCESS_KEY=<AWS_SECRET_ACCESS_KEY>' >> ~/.profile
      source ~/.profile
      ```

### [**Go**](https://go.dev/dl/) (>= v3.13.1)
```bash
wget https://dl.google.com/go/go1.13.6.linux-amd64.tar.gz
sudo tar -zxvf go1.13.6.linux-amd64.tar.gz -C /usr/local
sudo echo 'export PATH=$PATH:/usr/local/go/bin' >> ~/.profile
sudo echo 'export GOPATH=$HOME/go' >> ~/.profile
source ~/.profile
go version
```

### [**Java 11:**](https://www.digitalocean.com/community/tutorials/how-to-install-java-with-apt-on-ubuntu-20-04):
```bash
sudo apt install openjdk-11-jre
sudo apt install openjdk-11-jdk
sudo echo 'export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64' >> ~/.profile
source ~/.profile
echo $JAVA_HOME
javac -version
java -version
```

### Scala: 2.11.12
```bash
wget https://downloads.lightbend.com/scala/2.11.12/scala-2.11.12.deb
sudo dpkg -i scala-2.11.12.deb
sudo apt-get update
scala -version
```

### [sbt: 1.5.5](https://www.scala-sbt.org/download.html?_ga=2.195232236.1901884640.1633358692-54053138.1633358495)
```bash
  echo "deb https://repo.scala-sbt.org/scalasbt/debian all main" | sudo tee /etc/apt/sources.list.d/sbt.list
  echo "deb https://repo.scala-sbt.org/scalasbt/debian /" | sudo tee /etc/apt/sources.list.d/sbt_old.list
  curl -sL "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x2EE0EA64E40A89B84B2DF73499E82A75642AC823" | sudo apt-key add
  sudo apt-get update
  sudo apt-get install sbt=1.5.5
  sbt sbtVersion
```

### Ifrastructure as Code (IaC):
* Install [**Terraform**](https://learn.hashicorp.com/tutorials/terraform/install-cli)
  ```bash
  sudo apt-get update
  sudo apt-get install gnupg2
  curl https://apt.releases.hashicorp.com/gpg | gpg --dearmor > hashicorp.gpg
  curl -fsSL https://apt.releases.hashicorp.com/gpg | sudo apt-key add -
  sudo apt-add-repository "deb [arch=$(dpkg --print-architecture)] https://apt.releases.hashicorp.com $(lsb_release -cs) main"
  sudo apt-get update 
  sudo apt-get install terraform=1.1.9
  terraform --version
  ```