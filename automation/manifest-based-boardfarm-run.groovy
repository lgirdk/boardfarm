def extra_args = env.extra_args ?: ''
def email_results = env.email_results ?: ''
def GERRIT_BRANCH = env.GERRIT_BRANCH ?: 'master'
def GERRIT_PROJECT = env.GERRIT_PROJECT ?: ''
def GERRIT_REFSPEC = env.GERRIT_REFSPEC ?: ''

pipeline {
	agent { label 'boardfarm && ' + location }

	stages {
		stage('checkout gerrit change') {

			steps {
				sshagent ( [ ssh_auth ] ) {
					script {
						sh "rm -rf *"
						sh "repo init -u " + manifest + " && repo sync --force-remove-dirty"
						sh "repo forall -c 'git checkout gerrit/$GERRIT_BRANCH'"
						if (GERRIT_REFSPEC != '') {
							sh "repo forall -r ^$GERRIT_PROJECT\$ -c 'pwd && git fetch gerrit $GERRIT_REFSPEC && git checkout FETCH_HEAD && git rebase gerrit/$GERRIT_BRANCH'"
							def changes = sh returnStatus: true, script: "repo diff | diffstat | grep '0 files changed'"
							if (changes == 0) {
								echo "No changes with GERRIT trigger, ending job"
								return
							}
						}
						sh "repo manifest -r"
					}
				}
			}
		}

		stage('run bft test') {
			steps {
				ansiColor('xterm') {
					sh '''
					cd boardfarm
					pwd
					ls
					rm -rf venv
					virtualenv venv
					. venv/bin/activate
					repo forall -c '[ -e "setup.py" ] && { pip install -e . || echo failed; } || true '
					repo forall -c '[ -e "requirements.txt" ] && { pip install -r requirements.txt || echo failed; } || true '
					export BFT_OVERLAY="$(repo forall -c 'pwd' | grep -v boardfarm$ | tr '\n' ' ')"
					export BFT_CONFIG=''' + config + '''
					${WORKSPACE}/boardfarm/scripts/whatchanged.py --debug m/master HEAD ${BFT_OVERLAY} ${WORKSPACE}/boardfarm
					export changes_args="`${WORKSPACE}/boardfarm/scripts/whatchanged.py m/master HEAD ${BFT_OVERLAY} ${WORKSPACE}/boardfarm`"
					yes | BFT_DEBUG=y ./bft -b ''' + board + ''' -x ''' + testsuite + ''' ${changes_args}''' + extra_args

					sh 'grep tests_fail...0, boardfarm/results/test_results.json'
				}
			}
		}
		stage('post results to gerrit') {
			steps {
				sh '''#!/bin/bash
				cat boardfarm/results/test_results.json | jq '.test_results[] | [ .grade, .name, .message, .elapsed_time ] | @tsv' | \
				sed -e 's/"//g' -e 's/\\t/    /g' | \
				while read -r line; do
				echo $line >> message
				done
				'''
			}
		}
	}
	post {
		always {
			archiveArtifacts artifacts: 'boardfarm/results/*'
			sh 'rm -rf boardfarm/results'
			emailext body: '${SCRIPT, template="groovy-html.template"}',
				recipientProviders: [requestor()],
				subject: '[Jenkins] ${currentBuild.fullDisplayName} - ${currentBuild.currentResult}',
				to: email_results
		}
	}
}
