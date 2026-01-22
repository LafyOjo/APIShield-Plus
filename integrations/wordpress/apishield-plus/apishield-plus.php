<?php
/*
Plugin Name: APIShield Plus
Description: Adds APIShield Plus browser agent injection and login security event reporting.
Version: 0.1.0
Author: APIShield
*/

if (!defined('ABSPATH')) {
    exit;
}

define('APISHIELD_PLUS_OPTION_KEY', 'apishield_plus_settings');
define('APISHIELD_PLUS_RETRY_TRANSIENT', 'apishield_plus_retry_queue');
define('APISHIELD_PLUS_RETRY_HOOK', 'apishield_plus_retry_send');

function apishield_plus_default_settings() {
    return array(
        'public_key' => '',
        'secret_key' => '',
        'api_base_url' => '',
        'agent_url' => '',
        'brute_force_threshold' => 8,
        'brute_force_window' => 300,
    );
}

function apishield_plus_get_settings() {
    $defaults = apishield_plus_default_settings();
    $stored = get_option(APISHIELD_PLUS_OPTION_KEY, array());
    if (!is_array($stored)) {
        $stored = array();
    }
    return array_merge($defaults, $stored);
}

function apishield_plus_get_setting($key, $default = '') {
    $settings = apishield_plus_get_settings();
    if (array_key_exists($key, $settings)) {
        return $settings[$key];
    }
    return $default;
}

function apishield_plus_sanitize_settings($input) {
    $output = apishield_plus_default_settings();
    $output['public_key'] = isset($input['public_key']) ? sanitize_text_field($input['public_key']) : '';
    $output['secret_key'] = isset($input['secret_key']) ? sanitize_text_field($input['secret_key']) : '';
    $output['api_base_url'] = isset($input['api_base_url']) ? esc_url_raw($input['api_base_url']) : '';
    $output['agent_url'] = isset($input['agent_url']) ? esc_url_raw($input['agent_url']) : '';
    $output['brute_force_threshold'] = isset($input['brute_force_threshold'])
        ? max(1, intval($input['brute_force_threshold']))
        : $output['brute_force_threshold'];
    $output['brute_force_window'] = isset($input['brute_force_window'])
        ? max(60, intval($input['brute_force_window']))
        : $output['brute_force_window'];
    return $output;
}

function apishield_plus_admin_menu() {
    add_options_page(
        'APIShield Plus',
        'APIShield Plus',
        'manage_options',
        'apishield-plus',
        'apishield_plus_render_settings_page'
    );
}
add_action('admin_menu', 'apishield_plus_admin_menu');

function apishield_plus_settings_init() {
    register_setting('apishield_plus', APISHIELD_PLUS_OPTION_KEY, 'apishield_plus_sanitize_settings');

    add_settings_section(
        'apishield_plus_section_main',
        'APIShield Plus Settings',
        'apishield_plus_section_main_cb',
        'apishield_plus'
    );

    add_settings_field(
        'apishield_plus_public_key',
        'Public Key',
        'apishield_plus_public_key_render',
        'apishield_plus',
        'apishield_plus_section_main'
    );

    add_settings_field(
        'apishield_plus_secret_key',
        'Secret Key',
        'apishield_plus_secret_key_render',
        'apishield_plus',
        'apishield_plus_section_main'
    );

    add_settings_field(
        'apishield_plus_api_base_url',
        'API Base URL',
        'apishield_plus_api_base_url_render',
        'apishield_plus',
        'apishield_plus_section_main'
    );

    add_settings_field(
        'apishield_plus_agent_url',
        'Agent Script URL',
        'apishield_plus_agent_url_render',
        'apishield_plus',
        'apishield_plus_section_main'
    );

    add_settings_field(
        'apishield_plus_bruteforce_threshold',
        'Brute Force Threshold',
        'apishield_plus_bruteforce_threshold_render',
        'apishield_plus',
        'apishield_plus_section_main'
    );

    add_settings_field(
        'apishield_plus_bruteforce_window',
        'Brute Force Window (seconds)',
        'apishield_plus_bruteforce_window_render',
        'apishield_plus',
        'apishield_plus_section_main'
    );
}
add_action('admin_init', 'apishield_plus_settings_init');

function apishield_plus_section_main_cb() {
    echo '<p>Configure APIShield Plus to inject the browser agent and send login security events.</p>';
}

function apishield_plus_public_key_render() {
    $value = apishield_plus_get_setting('public_key');
    echo '<input type="text" name="' . esc_attr(APISHIELD_PLUS_OPTION_KEY) . '[public_key]" value="' . esc_attr($value) . '" class="regular-text" />';
}

function apishield_plus_secret_key_render() {
    $value = apishield_plus_get_setting('secret_key');
    echo '<input type="password" name="' . esc_attr(APISHIELD_PLUS_OPTION_KEY) . '[secret_key]" value="' . esc_attr($value) . '" class="regular-text" />';
    echo '<p class="description">Required for server-side security events.</p>';
}

function apishield_plus_api_base_url_render() {
    $value = apishield_plus_get_setting('api_base_url');
    echo '<input type="url" name="' . esc_attr(APISHIELD_PLUS_OPTION_KEY) . '[api_base_url]" value="' . esc_attr($value) . '" class="regular-text" />';
    echo '<p class="description">Example: https://api.yourdomain.com</p>';
}

function apishield_plus_agent_url_render() {
    $value = apishield_plus_get_setting('agent_url');
    echo '<input type="url" name="' . esc_attr(APISHIELD_PLUS_OPTION_KEY) . '[agent_url]" value="' . esc_attr($value) . '" class="regular-text" />';
    echo '<p class="description">Host the agent file from agent/dist/agent.js on your CDN or domain.</p>';
}

function apishield_plus_bruteforce_threshold_render() {
    $value = apishield_plus_get_setting('brute_force_threshold');
    echo '<input type="number" min="1" name="' . esc_attr(APISHIELD_PLUS_OPTION_KEY) . '[brute_force_threshold]" value="' . esc_attr($value) . '" class="small-text" />';
    echo '<p class="description">Number of failed logins before a brute force event is sent.</p>';
}

function apishield_plus_bruteforce_window_render() {
    $value = apishield_plus_get_setting('brute_force_window');
    echo '<input type="number" min="60" name="' . esc_attr(APISHIELD_PLUS_OPTION_KEY) . '[brute_force_window]" value="' . esc_attr($value) . '" class="small-text" />';
}

function apishield_plus_render_settings_page() {
    if (!current_user_can('manage_options')) {
        return;
    }
    echo '<div class="wrap">';
    echo '<h1>APIShield Plus</h1>';
    echo '<form action="options.php" method="post">';
    settings_fields('apishield_plus');
    do_settings_sections('apishield_plus');
    submit_button('Save Settings');
    echo '</form>';
    echo '</div>';
}

function apishield_plus_build_endpoint($api_base_url, $path) {
    $api_base_url = trim($api_base_url);
    if (!$api_base_url) {
        return '';
    }
    return rtrim($api_base_url, '/') . $path;
}

function apishield_plus_inject_agent() {
    if (is_admin()) {
        return;
    }
    $public_key = apishield_plus_get_setting('public_key');
    $agent_url = apishield_plus_get_setting('agent_url');
    if (!$public_key || !$agent_url) {
        return;
    }
    $api_base_url = apishield_plus_get_setting('api_base_url');
    $endpoint = apishield_plus_build_endpoint($api_base_url, '/api/v1/ingest/browser');

    echo "\n<!-- APIShield Plus Agent -->\n";
    echo '<script async src="' . esc_url($agent_url) . '" data-key="' . esc_attr($public_key) . '"';
    if ($endpoint) {
        echo ' data-endpoint="' . esc_url($endpoint) . '"';
    }
    echo '></script>' . "\n";
}
add_action('wp_head', 'apishield_plus_inject_agent', 5);

function apishield_plus_get_client_ip() {
    $candidates = array(
        'HTTP_X_FORWARDED_FOR',
        'HTTP_X_REAL_IP',
        'REMOTE_ADDR',
    );
    foreach ($candidates as $header) {
        if (!empty($_SERVER[$header])) {
            $value = sanitize_text_field(wp_unslash($_SERVER[$header]));
            if ($header === 'HTTP_X_FORWARDED_FOR') {
                $parts = explode(',', $value);
                $value = trim($parts[0]);
            }
            if ($value) {
                return $value;
            }
        }
    }
    return '';
}

function apishield_plus_current_path() {
    if (empty($_SERVER['REQUEST_URI'])) {
        return null;
    }
    $value = sanitize_text_field(wp_unslash($_SERVER['REQUEST_URI']));
    $parts = wp_parse_url($value);
    if (!empty($parts['path'])) {
        return $parts['path'];
    }
    return null;
}

function apishield_plus_hash_identifier($identifier) {
    $normalized = trim(strtolower((string) $identifier));
    if ($normalized === '') {
        return null;
    }
    return hash_hmac('sha256', $normalized, wp_salt('auth'));
}

function apishield_plus_send_security_event($payload) {
    $secret_key = apishield_plus_get_setting('secret_key');
    if (!$secret_key) {
        return;
    }
    $api_base_url = apishield_plus_get_setting('api_base_url');
    $endpoint = apishield_plus_build_endpoint($api_base_url, '/api/v1/ingest/security');
    if (!$endpoint) {
        return;
    }

    $args = array(
        'headers' => array(
            'Content-Type' => 'application/json',
            'X-Api-Secret' => $secret_key,
        ),
        'body' => wp_json_encode($payload),
        'timeout' => 4,
    );

    $response = wp_remote_post($endpoint, $args);
    $code = wp_remote_retrieve_response_code($response);
    if (is_wp_error($response) || $code < 200 || $code >= 300) {
        apishield_plus_enqueue_retry($payload);
    }
}

function apishield_plus_enqueue_retry($payload) {
    $queue = get_transient(APISHIELD_PLUS_RETRY_TRANSIENT);
    if (!is_array($queue)) {
        $queue = array();
    }
    if (count($queue) >= 50) {
        return;
    }
    $queue[] = array(
        'payload' => $payload,
        'attempts' => 1,
    );
    set_transient(APISHIELD_PLUS_RETRY_TRANSIENT, $queue, 3600);

    if (!wp_next_scheduled(APISHIELD_PLUS_RETRY_HOOK)) {
        wp_schedule_single_event(time() + 60, APISHIELD_PLUS_RETRY_HOOK);
    }
}

function apishield_plus_process_retry_queue() {
    $queue = get_transient(APISHIELD_PLUS_RETRY_TRANSIENT);
    if (!is_array($queue) || empty($queue)) {
        delete_transient(APISHIELD_PLUS_RETRY_TRANSIENT);
        return;
    }
    $remaining = array();
    foreach ($queue as $item) {
        if (empty($item['payload']) || !is_array($item['payload'])) {
            continue;
        }
        $attempts = isset($item['attempts']) ? intval($item['attempts']) : 1;
        if ($attempts > 3) {
            continue;
        }
        $payload = $item['payload'];
        $secret_key = apishield_plus_get_setting('secret_key');
        $api_base_url = apishield_plus_get_setting('api_base_url');
        $endpoint = apishield_plus_build_endpoint($api_base_url, '/api/v1/ingest/security');
        if (!$secret_key || !$endpoint) {
            continue;
        }
        $args = array(
            'headers' => array(
                'Content-Type' => 'application/json',
                'X-Api-Secret' => $secret_key,
            ),
            'body' => wp_json_encode($payload),
            'timeout' => 4,
        );
        $response = wp_remote_post($endpoint, $args);
        $code = wp_remote_retrieve_response_code($response);
        if (is_wp_error($response) || $code < 200 || $code >= 300) {
            $item['attempts'] = $attempts + 1;
            $remaining[] = $item;
        }
    }

    if (!empty($remaining)) {
        set_transient(APISHIELD_PLUS_RETRY_TRANSIENT, $remaining, 3600);
        wp_schedule_single_event(time() + 300, APISHIELD_PLUS_RETRY_HOOK);
    } else {
        delete_transient(APISHIELD_PLUS_RETRY_TRANSIENT);
    }
}
add_action(APISHIELD_PLUS_RETRY_HOOK, 'apishield_plus_process_retry_queue');

function apishield_plus_record_bruteforce($username) {
    $ip = apishield_plus_get_client_ip();
    if (!$ip) {
        return;
    }
    $threshold = apishield_plus_get_setting('brute_force_threshold');
    $window = apishield_plus_get_setting('brute_force_window');
    $cache_key = 'apishield_plus_fail_' . md5($ip);
    $count = get_transient($cache_key);
    if ($count === false) {
        $count = 0;
    }
    $count = intval($count) + 1;
    set_transient($cache_key, $count, $window);

    if ($count === intval($threshold)) {
        $payload = array(
            'ts' => gmdate('c'),
            'event_type' => 'brute_force',
            'severity' => 'high',
            'request_path' => apishield_plus_current_path(),
            'method' => isset($_SERVER['REQUEST_METHOD']) ? sanitize_text_field(wp_unslash($_SERVER['REQUEST_METHOD'])) : null,
            'status_code' => 429,
            'user_identifier' => apishield_plus_hash_identifier($username),
            'meta' => array(
                'failed_login_count' => $count,
                'window_seconds' => $window,
                'platform' => 'wordpress',
            ),
            'source' => 'wordpress',
        );
        apishield_plus_send_security_event($payload);
    }
}

function apishield_plus_handle_login_failed($username) {
    $payload = array(
        'ts' => gmdate('c'),
        'event_type' => 'login_attempt_failed',
        'severity' => 'medium',
        'request_path' => apishield_plus_current_path(),
        'method' => isset($_SERVER['REQUEST_METHOD']) ? sanitize_text_field(wp_unslash($_SERVER['REQUEST_METHOD'])) : null,
        'status_code' => 401,
        'user_identifier' => apishield_plus_hash_identifier($username),
        'meta' => array(
            'platform' => 'wordpress',
        ),
        'source' => 'wordpress',
    );
    apishield_plus_send_security_event($payload);
    apishield_plus_record_bruteforce($username);
}
add_action('wp_login_failed', 'apishield_plus_handle_login_failed', 10, 1);

function apishield_plus_handle_login_success($username, $user) {
    $payload = array(
        'ts' => gmdate('c'),
        'event_type' => 'login_attempt_succeeded',
        'severity' => 'low',
        'request_path' => apishield_plus_current_path(),
        'method' => isset($_SERVER['REQUEST_METHOD']) ? sanitize_text_field(wp_unslash($_SERVER['REQUEST_METHOD'])) : null,
        'status_code' => 200,
        'user_identifier' => apishield_plus_hash_identifier($username),
        'meta' => array(
            'platform' => 'wordpress',
        ),
        'source' => 'wordpress',
    );
    apishield_plus_send_security_event($payload);
}
add_action('wp_login', 'apishield_plus_handle_login_success', 10, 2);
