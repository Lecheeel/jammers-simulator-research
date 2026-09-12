if(window._wails&&window._wails.dispatchWailsEvent){var w=window._wails;w.__eq=(w.__eq||Promise.resolve()).then(function(){return fetch(%q,{cache:'no-store'}).then(function(r){return r.json();}).then(function(e){w.dispatchWailsEvent(e);});}).catch(function(){});}
		UPDATE upload_tasks
		SET formal_upload_state = 'outer_verifying', state = 'retry_wait', next_attempt_at_ms = ?,
			last_error_code = '', updated_at_ms = ?
		WHERE id = ? AND kind = 'formal_behavior' AND state = 'uploading' AND
			formal_upload_state IN ('intent_received','object_received','outer_verifying') AND upload_id <> ''
		UPDATE upload_tasks
		SET formal_upload_state = 'object_received', state = 'retry_wait', next_attempt_at_ms = ?,
			last_error_code = '', updated_at_ms = ?
		WHERE id = ? AND kind = 'formal_behavior' AND state = 'uploading' AND
			formal_upload_state IN ('intent_received','object_received','outer_verifying') AND upload_id <> ''
		UPDATE upload_tasks
		SET formal_upload_state = 'outer_verified',
			state = 'confirmed', next_attempt_at_ms = ?, last_error_code = '',
			received_at_ms = ?, updated_at_ms = ?
		WHERE id = ? AND kind = 'formal_behavior' AND state = 'uploading' AND
			formal_upload_state IN ('intent_received','object_received','outer_verifying') AND upload_id <> ''SELECT id, team_no, client_request_id, schema_version,
	activation_ticket_sha256, entered, end_reason, cleared_jammer_count,
	measure_accepted_count, virtual_time_us, program_run_duration_ms,
	channel_switch_count, clear_failure_count, state, attempt_count,
	next_attempt_at_ms, last_error_code, received_at_ms, created_at_ms, updated_at_ms
	FROM statistics_tasks 
		UPDATE upload_tasks
		SET upload_id = ?, upload_url = ?, formal_upload_state = 'intent_received', intent_received_at_ms = ?,
			state = 'queued', next_attempt_at_ms = ?, last_error_code = '', updated_at_ms = ?
		WHERE id = ? AND kind = 'formal_behavior' AND state = 'uploading' AND
			formal_upload_state = 'none' AND upload_id = '' AND intent_received_at_ms IS NULLSELECT id,team_no,client_request_id,schema_version,practice_ticket_sha256,problem_no,practice_run_no,case_code,entered,end_reason,cleared_jammer_count,measure_accepted_count,virtual_time_us,program_run_duration_ms,channel_switch_count,clear_failure_count,jammer_count,state,attempt_count,next_attempt_at_ms,last_error_code,received_at_ms,created_at_ms,updated_at_ms FROM practice_statistics_tasks SELECT
	id, kind, team_no, problem_no, practice_run_no, formal_index, case_code,
	authorization_ticket_sha256, activation_ticket_sha256, package_path, package_sha256,
	package_bytes, client_request_id, intent_request_sha256, upload_client_request_id,
	upload_id, upload_url, formal_upload_state, intent_received_at_ms, state, attempt_count,
	next_attempt_at_ms, last_error_code, received_at_ms, created_at_ms, updated_at_ms
	FROM upload_tasks 
		INSERT OR IGNORE INTO statistics_tasks (
			team_no, client_request_id, schema_version, activation_ticket_sha256,
			entered, end_reason, cleared_jammer_count, measure_accepted_count,
			virtual_time_us, program_run_duration_ms, channel_switch_count,
			clear_failure_count, state, attempt_count, next_attempt_at_ms,
			last_error_code, received_at_ms, created_at_ms, updated_at_ms
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', 0, ?, '', NULL, ?, ?)<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="color-scheme" content="light" />
    <title>