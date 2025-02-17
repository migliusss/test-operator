import asyncio
import time
import kopf
import kubernetes.client as k8s_client
import kubernetes.config as k8s_config
from kubernetes.client.rest import ApiException

# Load Kubernetes configuration.
k8s_config.load_incluster_config()

# Handlers monitor the behavior of the CR.
# They are called when any CR is created, modified or deleted and define how the operator should respond to events.
@kopf.on.create('kopf.dev', 'v1', 'databaseupdates')
@kopf.on.update('kopf.dev', 'v1', 'databaseupdates')
async def handle_database_update(spec, status, name, namespace, logger, **kwargs):
    desired_version = spec.get('version')
    current_version = status.get('currentVersion', '')

    # A Job ensures (by monitoring) that a specified number of Pods
    # run successfully until a given task is done f.eks. DB Migration. It has a start and an end.
    # If failed, it restarts the Job until success or a defined retry limit is reached.
    # It works by creating one or more pods to run a task.

    # The Operator does the following:
    # 1. Check current DB version with the desired DB version.
    # 2. Trigger a Job by creating a manifest for a Job.
    # 3. Create the Job.
    # 4. Monitor the job by polling for the Job until it completes or fails.

    # Step 1: Check current DB version with the desired DB version.
    if desired_version == current_version:
        logger.info("Database already at desired version: %s", desired_version)

        return {'currentVersion': current_version}

    # Step 2: Trigger a Job by creating a manifest for a Job.
    logger.info(f"Database update required: {current_version} -> {desired_version}")

    job_name = f"{name}-{desired_version}-job"
    job_manifest = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": job_name,
            "labels": {
                "app": "db-update",
                "dbupdate_cr": name,
            }
        },
        "spec": {
            "ttlSecondsAfterFinished": 200, # This deletes the job automatically after 200 secs, both if Success or Fail.
            "template": {
                "metadata": {
                    "labels": {
                        "app": "db-update",
                    }
                },
                "spec": {
                    "restartPolicy": "Never",
                    # Image for the script.
                    "containers": [
                        {
                            "name": "db-update",
                            "image": "migliuss/job-script-image",
                            "env": [
                                # Add any additional environment variables (e.g., credentials)
                                {
                                    "name": "TARGET_DB_VERSION",
                                    "value": desired_version,
                                }
                            ]
                        }
                    ]
                }
            }
        }
    }

    # Step 3: Create the Job.
    # Use BatchV1Api for Job creation: https://github.com/kubernetes-client/python/blob/master/kubernetes/docs/BatchV1Api.md#patch_namespaced_job
    batch_v1 = k8s_client.BatchV1Api()
    try:
        batch_v1.create_namespaced_job(namespace=namespace, body=job_manifest)
        logger.info(f"Job {job_name} created successfully")
    except ApiException as e:
        if e.status == 409:
            logger.info(f"Job {job_name} already exists")
        else:
            logger.error(f"Failed to create job: {job_name}, {e}")
            raise kopf.TemporaryError("Failed to create job", delay=30)

    # Step 4: Poll for the Job until it completes or fails.
    for _ in range(36):  # Polling the job status every 5 seconds, up to 3 minutes. May need to increase depending on how long it takes to finnish the Job.
        job = batch_v1.read_namespaced_job(name=job_name, namespace=namespace)
        # job.status.succeeded returns an int which is the number of pods which reached phase "Succeeded".
        # https://github.com/kubernetes-client/python/blob/master/kubernetes/docs/V1JobStatus.md
        if job.status.succeeded and job.status.succeeded >= 1:
            logger.info(f"Job {job_name} succeeded")
            break
        await asyncio.sleep(5)
    else:
        logger.error(f"Failed to create job: {job_name}")
        raise kopf.TemporaryError("Job did not complete", delay=30)

    logger.info("Database update complete. Setting currentVersion to %s", desired_version)

    deployment_name = "app-deployment"
    update_deployment_env(namespace, deployment_name, desired_version, logger)

    return {'currentVersion': desired_version}

def update_deployment_env(namespace: str, deployment_name: str, new_version: str, logger):
    apps_api = k8s_client.AppsV1Api()

    patch_body = {
        "spec" : {
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": "simple-kubernetes-app",
                            # This patch will replace the container’s existing env list.
                            # Specify all the env variables the app has.
                            "env": [
                                {
                                    "name": "APP_VERSION",
                                    "value": new_version
                                }
                            ]
                        }
                    ]
                }
            }
        }
    }

    try:
        apps_api.patch_namespaced_deployment(
            name=deployment_name,
            namespace=namespace,
            body=patch_body
        )
        logger.info(f"Deployment '{deployment_name}' updated to use APP_VERSION={new_version}s")
    except Exception as e:
        logger.error(f"Failed to update deployment '{deployment_name}': {str(e)}")
        raise

if __name__ == "__main__":
    kopf.run()