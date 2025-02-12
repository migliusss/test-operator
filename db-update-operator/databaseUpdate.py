import asyncio
import kopf
import kubernetes.config as k8s_config

# Load Kubernetes configuration.
k8s_config.load_incluster_config()

# Handlers monitor the behavior of the CR.
# They are called when any CR is created, modified or deleted and define how the operator should respond to events.
@kopf.on.create('kopf.dev', 'v1', 'databaseupdates')
@kopf.on.update('kopf.dev', 'v1', 'databaseupdates')
async def handle_database_update(spec, status, namespace, logger, **kwargs):
    desired_version = spec.get('version')
    current_version = spec.get('currentVersion', '')

    if desired_version == current_version:
    # A Job ensures (by monitoring) that a specified number of Pods
    # run successfully until a given task is done f.eks. DB Migration. It has a start and an end.
    # If fail, it restarts the Job until success or a defined retry limit is reached.
    # It works by creating one or more pods to run a task.

    # The Operator should:
    # 1. Trigger the Job.
    # 2. Monitor its progress and wait for it to finnish.
    # 3. Update the custom resource's status.
    # 4. Update the Deployment.
        logger.info("Database already at desired version: %s", desired_version)
        return {'currentVersion': current_version}

    logger.info("Database update required: %s -> %s", current_version, desired_version)
    await asyncio.sleep(10)

    logger.info("Database update complete. Setting currentVersion to %s", desired_version)
    return {'currentVersion': desired_version}

if __name__ == "__main__":
    kopf.run()