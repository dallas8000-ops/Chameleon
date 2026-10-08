ERRORS = {
    "provider_not_configured": "Configure Magic Hour on the server.",
    "pricing_unavailable": "Verified pricing is unavailable; no provider request was started.",
    "quote_changed": "Pricing changed before submission; no provider request was started.",
    "workspace_read_only": "Requester authorization changed; no provider request was started.",
    "not_found": "Generation scope is no longer available; no provider request was started.",
    "download_origins_unavailable": "Private download origins are unavailable.",
    "storage_unavailable": "Durable private storage is not confirmed.",
    "provider_poll_exhausted": "Tracking is exhausted; resume existing tracking, do not generate again.",
    "provider_poll_unavailable": "Tracking is delayed; the existing job will be recovered.",
    "provider_submission_outcome_unknown": "The provider may have charged this request. Do not resubmit; operator reconciliation is required.",
    "provider_submission_tracking_closed": "Operator closed local tracking; this does not confirm a refund or authorize resubmission.",
}


def safe_job_error(job):
    if not job.error_code:
        return "", ""
    if job.error_code in ERRORS:
        return job.error_code, ERRORS[job.error_code]
    return "provider_tracking_error", "Provider or tracking reported an error. Do not automatically generate again."
