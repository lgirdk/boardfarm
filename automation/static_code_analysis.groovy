def checkout_repos () {
        sh """
            rm -rf *
            repo init -u ssh://jenkins@cicd.lgirdk.com:29418/lgi/manifest -m default.xml
            repo sync --force-sync --force-remove-dirty -m default.xml
            repo forall -c "git rev-parse HEAD"
        """
}


def setup_python () {
    println("Setting up Python 3")
    sh """
        rm -rf venv3
        python3 -m venv venv3
        . venv3/bin/activate
        pip3 install --upgrade pip
        pip3 install wheel
        python3 --version
        pip3 --version
        repo forall -c '[ -e "requirements.txt" ] && { pip3 install -r requirements.txt || echo failed; } || true '
        repo forall -c '[ -e "setup.py" ] && { pip3 install -e . || echo failed; } || true '
    """
}


def run_unittest () {
    println("Running unittests")
    sh """
        set +e
        . venv3/bin/activate
        repo forall -c '[ -d "unittests" ] && {pytest unittests --junit-xml=unittest_results.xml}'
    """
}


def pytest_coverage () {
    println("Running pytest coverage")
    sh """
        set +e
        . venv3/bin/activate
        repo forall -c '[ -d "unittests" ] && export REPO_NAME=\$(echo \$REPO_PROJECT | cut -d'/' -f2 | sed "s/-/_/g") && { pytest --cov-config=.coveragerc --cov-report=xml:coverage_results.xml --cov=\$REPO_NAME unittests/ || echo failed; } || true'
    """
}


def sonar_scanner () {
    println("Running sonar scanner")
    def scannerHome = tool 'SonarQubeScanner'
    def url = sh(script: "awk /url/  /home/jenkins/bin/.sonar_config.ini |awk '{print \$NF}'", returnStdout: true).trim()
    def token = sh(script: "awk /token/  /home/jenkins/bin/.sonar_config.ini |awk '{print \$NF}'", returnStdout: true).trim()
    withSonarQubeEnv('SonarQube') {
        sh """
           export PATH=${scannerHome}/bin/:$PATH
           set +e
           . venv3/bin/activate
           repo forall -c 'sonar-scanner -Dsonar.sources=. -Dsonar.projectKey=\$REPO_PROJECT -Dsonar.host.url=${url} -Dsonar.login=${token}'
       """
   }
}


pipeline {
    agent { label 'boardfarm' }
    stages {
        stage('checkout repositores and set python') {
            steps {
                script {
                    checkout_repos ()
                    setup_python ()
                }
            }
        }
        stage('run pytest coverage') {
            steps {
                script {
                    pytest_coverage ()
                }
            }
        }
        stage('run sonar scanner') {
            steps {
                script {
                    sonar_scanner ()
                }
            }
        }
    }
    post {
        always {
            script {
                cleanWs()
            }
        }
    }
}
