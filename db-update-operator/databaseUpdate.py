import asyncio
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
async def handle_database_update(spec, status, namespace, logger, **kwargs):
    desired_version = spec.get('version')
    current_version = spec.get('currentVersion', '')

    # Step 1: Check current DB version with the desired DB version.
    if desired_version == current_version:
        logger.info("Database already at desired version: %s", desired_version)

        return {'currentVersion': current_version}

    # A Job ensures (by monitoring) that a specified number of Pods
    # run successfully until a given task is done f.eks. DB Migration. It has a start and an end.
    # If failed, it restarts the Job until success or a defined retry limit is reached.
    # It works by creating one or more pods to run a task.

    # The Operator should:
    # 1. Trigger the Job.
    # 2. Monitor its progress and wait for it to finnish.
    # 3. Update the custom resource's status.
    # 4. Update the Deployment.

    # Step 2: Create a manifest for a Job.
    logger.info("Database update required: %s -> %s", current_version, desired_version)

    job_name = f"{name}-job"
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
                            "image": "migliuss/job-script-image:latest",
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
        batch_v1.create_namespaced_jon(namespace, job_manifest)
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
        # job.status.succeeded returns an int which is the number of pods which reached phase Succeeded.
        # https://github.com/kubernetes-client/python/blob/master/kubernetes/docs/V1JobStatus.md
        if job.status.succeeded and job.status.succeeded >= 1:
            logger.info(f"Job {job_name} succeeded")
            break
        time.sleep(5)
    else:
        logger.error(f"Failed to create job: {job_name}")
        raise kopf.TemporaryError("Job did not complete", delay=30)

    logger.info("Database update complete. Setting currentVersion to %s", desired_version)
    return {'currentVersion': desired_version}

if __name__ == "__main__":
    kopf.run()