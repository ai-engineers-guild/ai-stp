rule ai_stp_malware_test_marker
{
  meta:
    description = "Platform malware test marker for fixture scans"
  strings:
    $a = "AI_STP_MALWARE_TEST_MARKER_V1" ascii
  condition:
    $a
}
