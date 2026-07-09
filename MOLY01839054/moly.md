# MOLY01839054 (MOLY) — Notes Dump

## CR Meta

- Title: [MD PSIRT][MSV-7865][External Feedback]Security Vulnerability in Modem - MTK_5G_NR_Modem_DoS_via_Malformed_pdsch-AggregationFactor_in_RRCSetup (H1#3592187)
- State: Resolved
- Priority: 2.Medium
- Severity: Critical
- Project: {'Pm.fullname': 'WCP Admin', 'Pm.Phone': '', 'Customer_Company': 'MTK', 'Csi.fullname': '', 'Security_Level': 'Public', 'Csi.Phone': '', 'Name': "'@General", 'Extension_Models': '', 'Pm.login_name': 'wcpadmin', 'Security_Control': '', 'Product_Line': '', 'dbid': '33576044', 'DisplayName': "'@General", 'Csi.login_name': '', 'Pm': 'wcpadmin'}
- Platform: MOLY
- Submit Date: 2026-03-09 13:05:37
- Assignee: Yen-chieh Huang (login={'Department': 'csd_msp_msp18', 'login_name': 'mtk14968', 'is_active': '1', 'phone': '34221', 'dbid': '62259256', 'DisplayName': 'mtk14968', 'fullname': 'Yen-chieh Huang', 'email': 'yen-chieh.huang@mediatek.com'}) — Dept csd_msp_msp18
- Be_Related_Crs: []
- Sync_Cr_Id: 

## Description
```
h1. Vulnerability Report: 5G NR Modem ASSERT via Malformed pdsch-AggregationFactor in RRCSetup

h2. Summary

A denial-of-service vulnerability was identified in the MediaTek Dimensity 1200 (MT6893) 5G NR modem. When a rogue base station sends a crafted RRCSetup message with the {{pdsch-AggregationFactor}} field set in the PDSCH-Config, the modem's DPC coprocessor interrupt service routine triggers an ASSERT failure. This causes a modem crash (subsystem restart), and upon reconnection the crash recurs, resulting in a cascading failure.

h2. Vulnerability Details

|| Field || Value ||
| *Affected Component* | MediaTek 5G NR Modem (DPC Coprocessor) |
| *Crash Location* | {{mcu/driver/dpcopro/src/dpcopro_hisr.c}} line 811 |
| *Crash Type* | {{[ASSERT]}} - unrecoverable assertion failure |
| *ASSERT Parameters* | p1=0x00000000, p2=0x00000000, p3=0x00000000 |
| *Crash Reason* | {{bwp}} (Bandwidth Part handling failure) |
| *Impact* | Modem reset → repeated crash (DoS) |
| *Attack Vector* | Over-the-air via rogue gNB (fake base station) |
| *Trigger Message* | RRCSetup (DL-CCCH) with {{pdsch-AggregationFactor}} field set to {{n2}} |

h2. Affected ASN.1 Field

The vulnerability is triggered by adding a normally absent OPTIONAL field in the RRCSetup CellGroupConfig:

{code}
RRCSetup
  └─ masterCellGroup (CellGroupConfig)
      └─ spCellConfig
          └─ spCellConfigDedicated (ServingCellConfig)
              └─ initialDownlinkBWP
                  └─ pdsch-Config (SETUP)
                      └─ pdsch-AggregationFactor: n2   ← ADDED (absent in baseline)
{code}

The {{pdsch-AggregationFactor}} field (3GPP TS 38.331) specifies the number of PDSCH transmissions for slot aggregation. Valid enum values are {{{n2, n4, n8}}}. This field is optional and typically not present in standard RRCSetup messages. When this field is present with value {{n2}}, the modem's DPC coprocessor attempts to configure slot aggregation during DL signal processing but encounters an invalid internal state in the high-priority interrupt service routine (HISR), triggering the assertion.

h2. Seed Construction

The PoC payload (156 bytes) was constructed as follows:

1. *Baseline capture*: A legitimate RRCSetup message was captured from a real 5G NR connection between the test gNB and UE
2. *Selective modification*: The UPER-encoded CellGroupConfig was modified to enable the {{pdsch-AggregationFactor}} OPTIONAL field with value {{n2}}, which is absent in the original baseline message
3. *Binary encoding*: The modification is a syntactically valid ASN.1 UPER encoding

h2. Steps to Reproduce

h3. Environment
- Laptop with Linux, connected to *USRP B210* SDR
- Modified 5ghoul Docker container with extended RRCSetup message injection support (based on https://github.com/asset-group/5ghoul-5g-nr-attacks and OAI 5G SA)
- A packaged Docker image with the PoC and reproduction environment will be provided separately

h3. Reproduction Steps

1. Set up the rogue gNB environment using the provided Docker image with USRP B210
2. The gNB is configured to send the modified RRCSetup message (with {{pdsch-AggregationFactor=n2}} in PDSCH-Config) to any connecting UE
3. Place the target phone near the USRP B210 antenna and toggle airplane mode OFF to initiate connection
4. The phone will perform RACH → receive the modified RRCSetup → modem ASSERT triggers within ~15 seconds
5. Expected result: modem crashes, phone loses all cellular connectivity

h2. Target Device Information

|| Field || Value ||
| *Device* | Redmi K40 Gaming (M2012K10C) |
| *SoC* | MediaTek Dimensity 1200 (MT6893) |
| *Android Version* | 13 |
| *Security Patch Level* | 2023-04-01 |
| *Modem Firmware* | MOLY.NR15.R3.TC8.PR2.SP.V2.1.P70 |
| *Build Fingerprint* | Redmi/ares/ares:13/TP1A.220624.014/V14.0.3.0.TKJCNXM:user/release-keys |
| *Platform* | mt6893 |

h2. Crash Timeline (from adb logcat)

|| Time || Event ||
| 10:57:09.736 | {{md_modem_reboot_ind_hdlr}} — modem reboot indication |
| 10:57:13.229 | *CCCI_MD_MSG_EXCEPTION* — modem exception (1st) |
| 10:57:20.928 | *[ASSERT] dpcopro_hisr.c:811* — 1st ASSERT (p1=0, p2=0, p3=0) |
| 10:57:40.720 | Digest: {{MCU_core, ELM r/wlat:PASS, subsystem_modem}} |
| 10:57:40.817 | {{modemCrashReasons = bwp}}, modem SSR |
| 10:57:40.813 | {{UNSOL_MODEM_RESTART}} — modem SSR begins |
| 10:57:50.271 | *CCCI_MD_MSG_EXCEPTION* — 2nd modem exception (re-crash) |
| 10:57:57.776 | *[ASSERT] dpcopro_hisr.c:811* — 2nd ASSERT (identical) |


h2. Reproducibility

This vulnerability has been independently reproduced twice on the same device:

|| || Run 1 (Batch Test) || Run 2 (Manual Reproduce) ||
| *Date* | 2026-03-08 06:06 | 2026-03-08 10:57 |
| *ASSERT location* | {{dpcopro_hisr.c:811}} | {{dpcopro_hisr.c:811}} |
| *Crash reason* | {{bwp}} | {{bwp}} |
| *ASSERT count* | 2 (modem SSR → re-crash) | 2 (modem SSR → re-crash) |
| *Time to crash* | ~12s after radio on | ~12s after radio on |

Both runs produced identical crash signatures, confirming the vulnerability is deterministic and reliably reproducible.

h2. Supporting Materials

{code}
v107_evidence/
├── poc/
│   ├── v_107_pdsch-AggregationFactor_e0.bin   # PoC payload (156 bytes)
│   └── v_107_pdsch-AggregationFactor_e0.xml   # ASN.1 XML
├── logs/
│   ├── phone_log_run1.log                     # adb logcat — batch test discovery
│   ├── phone_log_run2_reproduce.log           # adb logcat — independent reproduction
│   └── events_run2_reproduce.txt              # 5ghoul events — reproduction
└── pcap/
    └── capture_run2_reproduce.pcapng          # Wireshark trace — reproduction
{code}

h2. Testing Methodology and Ongoing Work

This vulnerability was discovered using a custom-developed automated OTA fuzzing tool that systematically mutates individual ASN.1 fields within the RRCSetup CellGroupConfig message and injects them over the air via a USRP B210 SDR running the 5ghoul framework.

*We have recently completed development of this fuzzing tool and are actively expanding testing to additional chipsets and newer devices.* Results from those tests will be reported separately as they become available.

h2. Impact

h2. Impact

h3. Severity: High (DoS)

1. *Immediate impact*: The device's 5G NR modem crashes upon receiving the crafted RRCSetup message, losing all cellular connectivity (voice, data, emergency calls)

2. *Persistent impact*: The modem automatically attempts to reconnect after SSR (subsystem restart). Since the rogue gNB is still transmitting, the same malformed RRCSetup is delivered again, causing a second crash

3. *Recovery*: The device requires a complete reboot to restore normal network functionality. If the rogue gNB remains active, the device will crash again upon reconnection

4. *Attack characteristics*:
- No user interaction required (passive attack — device connects to strongest signal)
- The payload is a syntactically valid ASN.1 message (passes format validation)
- Adding one OPTIONAL field with a valid enum value triggers the crash
- Potentially affects all devices using the same MediaTek modem firmware
```

## Notes (24 total — sorted ASC)

### Note 1 — 2026-03-09 13:12:14 — srv_nlp_logtime001 (srv_nlp_logtime001) — Mode: Internal Use

```
Log AI Detection Result

2026-03-09 13:12:10, [Add logURL Fail] get log fail: not transfer/share path
2026-03-09 13:12:10, [Add logURL Fail] get log fail: not transfer/share path
2026-03-09 13:22:59, [Add logURL Fail] get log fail: not transfer/share path (retry)
2026-03-09 13:22:59, [Add logURL Fail] get log fail: not transfer/share path (retry)
2026-03-09 14:10:11, [Add logURL Fail] get log fail: not transfer/share path (retry)
2026-03-09 14:10:11, [Add logURL Fail] get log fail: not transfer/share path (retry)
2026-03-09 14:10:41, [Add logURL Fail] get log fail: not transfer/share path (retry)
2026-03-09 14:10:41, [Add logURL Fail] get log fail: not transfer/share path (retry)

2026-03-23 11:50:36

Type and IDPath and FileActionAttribute
AttachmentMSV-7865_1.rarPost CAPDUT
AttachmentMSV-7865_2.rarPost CAPDUT
2026-03-23 11:50:36

Type and IDPath and FileActionAttribute
AttachmentG99_Jayer_R2MP_OF_Pass_20260323.rarPost CAPREF


*** Below are script records. Please user ignore this. ***
[JSON_START][{"Who": "LogAIComm", "When": "2026-03-09 13:12:10", "exec_status": "[Add logURL Fail] get log fail: not transfer/share path", "assign_date": "2026-03-09 13:05:41", "log_url": [], "file_name": [], "attr": [], "status": [], "logurl_id": [], "token_num": {"time": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, "dut_ref": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}}, {"Who": "LogAIComm", "When": "2026-03-09 13:12:10", "exec_status": "[Add logURL Fail] get log fail: not transfer/share path", "assign_date": "2026-03-09 13:05:41", "log_url": [], "file_name": [], "attr": [], "status": [], "logurl_id": [], "token_num": {"time": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, "dut_ref": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}}, {"Who": "LogAIComm", "When": "2026-03-09 13:22:59", "exec_status": "[Add logURL Fail] get log fail: not transfer/share path (retry)", "assign_date": "2026-03-09 13:05:41", "log_url": [], "file_name": [], "attr": [], "status": [], "logurl_id": [], "token_num": {"time": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, "dut_ref": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}}, {"Who": "LogAIComm", "When": "2026-03-09 13:22:59", "exec_status": "[Add logURL Fail] get log fail: not transfer/share path (retry)", "assign_date": "2026-03-09 13:05:41", "log_url": [], "file_name": [], "attr": [], "status": [], "logurl_id": [], "token_num": {"time": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, "dut_ref": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}}, {"Who": "LogAIComm", "When": "2026-03-09 14:10:11", "exec_status": "[Add logURL Fail] get log fail: not transfer/share path (retry)", "assign_date": "2023-01-02 00:00:00", "log_url": [], "file_name": [], "attr": [], "status": [], "logurl_id": [], "token_num": {"time": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, "dut_ref": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}}, {"Who": "LogAIComm", "When": "2026-03-09 14:10:11", "exec_status": "[Add logURL Fail] get log fail: not transfer/share path (retry)", "assign_date": "2023-01-02 00:00:00", "log_url": [], "file_name": [], "attr": [], "status": [], "logurl_id": [], "token_num": {"time": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, "dut_ref": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}}, {"Who": "LogAIComm", "When": "2026-03-09 14:10:41", "exec_status": "[Add logURL Fail] get log fail: not transfer/share path (retry)", "assign_date": "2023-01-02 00:00:00", "log_url": [], "file_name": [], "attr": [], "status": [], "logurl_id": [], "token_num": {"time": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, "dut_ref": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}}, {"Who": "LogAIComm", "When": "2026-03-09 14:10:41", "exec_status": "[Add logURL Fail] get log fail: not transfer/share path (retry)", "assign_date": "2023-01-02 00:00:00", "log_url": [], "file_name": [], "attr": [], "status": [], "logurl_id": [], "token_num": {"time": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, "dut_ref": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}}, {"Who": "LogAIComm", "When": "2026-03-23 11:50:36", "exec_status": "[Add logURL Success] logurl/POST all succ (note)", "assign_date": "2023-01-01 00:00:00", "log_url": ["NewAttachments", "NewAttachments"], "file_name": [["MSV-7865_1.rar"], ["MSV-7865_2.rar"]], "attr": [["DUT"], ["DUT"]], "status": ["post to CAP succ", "post to CAP succ"], "logurl_id": ["", ""], "token_num": {"time": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, "dut_ref": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}}, {"Who": "LogAIComm", "When": "2026-03-23 11:50:36", "exec_status": "[Add logURL Success] logurl/POST all succ (note)", "assign_date": "2023-01-01 00:00:00", "log_url": ["NewAttachments"], "file_name": [["G99_Jayer_R2MP_OF_Pass_20260323.rar"]], "attr": [["PASS", "REF", "RULE"]], "status": ["post to CAP succ"], "logurl_id": [""], "token_num": {"time": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, "dut_ref": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}}]
```

### Note 2 — 2026-03-09 14:07:34 — Benjamin Kuo (mtk04334) — Mode: Internal Use

```



Hi, MD PSIRT Lv1 PSE:

This is MediaTek Security team.

We received a potential security vulnerability report from an external security researcher.

Please help dispatch and coordinate the assessment for this security issue with module owner.

The severity of this issue is temporarily treated asHigh. So please handle with priority.




Please refer to the security report/POC and confirm if it's a security issue or not within3 daysaccording to the MediaTek Security Incident Response Time (1):




---

(1) MediaTek Security Incident Response Time:https://wiki.mediatek.inc/display/SPSM/Guideline+for+Security+Incident+Handling

(2) MD PSIRT Issue Handling Guideline:https://wiki.mediatek.inc/display/WTGPSWG/PSIRT+Issue+Handling+Guideline
(3) PSIRT Working Flow on Jira System:PSIRT Issue Handling Guideline

---

Thanks,

MediaTek Security Team
```

### Note 3 — 2026-03-09 14:08:36 — srv_cap (srv_cap) — Mode: CAP_AutoProcResult

```
CAP Dashboard:https://newcap.mediatek.inc/dashboard/cap-result/MOLY01839054
Please refer towikifor detailed information of CAP

2026-03-09 14:08:33 CAP processed file: F5491096_v107_evidence.zip (from attachment)
2026-03-13 14:15:20 CAP processed file: F5523263_phone_log_reproduce3.log (from attachment)
2026-03-23 11:44:07 CAP processed file: MSV-7865_1.rar (from attachment)
2026-03-23 11:44:41 CAP processed file: MSV-7865_2.rar (from attachment)
2026-03-23 11:45:34 CAP processed file: G99_Jayer_R2MP_OF_Pass_20260323.rar (from attachment)
2026-03-24 07:33:11 CAP processed file: BIN+ELF-202603181021_66677153_build563385.zip (from attachment)
2026-04-08 15:30:07 CAP processed file: BIN+ELF-202604081505_66843367_build571012.zip (from attachment)
```

### Note 4 — 2026-03-09 14:09:41 — srv_cqsrv_hbgsm001 (srv_cqsrv_hbgsm001) — Mode: Internal Use

```
External - HackerOne Comment ID: 39909690
qiqingh posted a comment:
h1. Supplementary Material — v_107 (pdsch-AggregationFactor)

h2. PCAP Correction

The pcap file submitted in the original report was empty (0 bytes). This is because the modem crashes immediately upon receiving the malformed RRCSetup — before the RRC connection completes — so the gNB-side pcap logger does not capture the full exchange.

The attached {{capture_run1.pcapng}} (1.1 MB) is the batch-level pcap from the automated test session that originally discovered this vulnerability. It covers the full batch of 20 seeds tested in the same gNB session, including the crash-triggering seed (v_107). The RRCSetup message carrying the malformed {{pdsch-AggregationFactor}} field can be identified by correlating with the crash timestamp in the phone log (06:06:16 EDT).

h2. Attached File
- {{capture_run1.pcapng}} — Wireshark trace from batch test session (batch_005, 20 seeds)
[^F5491198_capture_run1.pcapng]

Attachment: [^F5491198_capture_run1.pcapng]
```

### Note 5 — 2026-03-09 14:09:42 — srv_cqsrv_hbgsm001 (srv_cqsrv_hbgsm001) — Mode: Internal Use

```
External - HackerOne Comment ID: 39913840
mt_miles posted a comment:
Hi,

Thank you for your submission. We have received your report and it is now being assessed. We appreciate your patience in the meantime and will update you once we have more information about the status of the report.

The typical lifecycle for MediaTek Security Team to handle a security vulnerability is as follows:
1. Report will be triaged once the component owner has confirmed the issue.
2. MediaTek Security Team conducts an initial severity rating assessment based on CVSS v3.1.
3. Development of a fix.
4. MediaTek Security Team assigns a CVE (if this is Critical/High/Medium severity) and updates your CVE to this report.
5. MediaTek shared the fix under NDA to MediaTek OEM partners for remediation through the monthly Partner Security Bulletin.
6. Release in a public [MediaTek Product Security Bulletin|https://corp.mediatek.com/product-security-bulletin] (after sharing with MediaTek OEM partners for two months).
7. Publish your CVE with acknowledgement information on [MediaTek Product Security Acknowledgements|https://corp.mediatek.com/product-security-acknowledgements].
8. Bounty payment for report (if applicable).

To protect end-users using products powered by MediaTek chipsets, if you plan to publicly disclose the vulnerability(s) you found, including paper published in a conference, please kindly notify us through “security@mediatek.com”.

Thanks,
MediaTek Security Team
```

### Note 6 — 2026-03-09 14:09:43 — srv_cqsrv_hbgsm001 (srv_cqsrv_hbgsm001) — Mode: Internal Use

```
External - HackerOne Comment ID: 39913865
mt_miles posted an internal comment:
@mtk_benjamin  Please help create an internal issue ticket! In the sidebar, please help fill out: 1. Module Name (Please make sure the {{Affected Module}} list in PSIRT system has the same item)  2. Area  3. Severity rating in "Review_Severity_MemberX"  4. Write Up (A short description on your severity assessment). Once the module owner has confirmed it a valid issue, please change the status to {{Triage}}.
Security Vulnerability Handling Policy: https://wiki.mediatek.inc/display/PSO/Security+Vulnerability+Handling+Policy
```

### Note 7 — 2026-03-10 13:22:18 — srv_protocolone (srv_protocolone) — Mode: Protocol One

```
[ProtocolOne First Entry] Lv3 : srv_xrrc_nrrc_config
Dispatch_mechanism : round_robin
Owner : Chia-chun Huang
Owner_dept : wcs_mse5_ps6
Role :

[Reference] Gen list :
Gen97
Gen97 Colgin
Gen98
Gen98 Bollinger
Gen99R
Gen99R Customer
Gen99p1
Gen99p1+
Gen99p2
```

### Note 8 — 2026-03-10 15:08:39 — Chia-chun Huang (mtk26029) — Mode: Issue Analysis

```



Note Template: [Protocol One Analysis Report]



Please select the Current Moudle(s) in Module Info panel, and procide the Analysis Result of the module(s) below.




Please written in English, and refer to Wiki for the guideline (v20251125)
https://wiki.mediatek.inc/display/ProtocolOne/Analysis+Report+Template




[Summary]






Update current status and observation from NRRC_CONFIG.

1. Currently no available log.

2. Assert is not in RRC side, it's in "*[ASSERT] dpcopro_hisr.c:811* — 1st ASSERT (p1=0, p2=0, p3=0) |" Per CR Description.

3. For the mentioned IE,  pdsch-AggregationFactor is within value range and comply with the spec limitation.

4. Check PSIRT  CR from 2024 - 2026, no similar PSIRT issue found in either CR record or Code base presents special handling in 99 for this IE.

5. Reproduce same IE handling mentioned from description using GUEST: RRC handling is pass and no assertion/fatal observed. (See below)






Conclusion from NRRC_CONFIG:

- Need assert file owner help to conclude what cause the assertion.





[Issue Description]

Check if the PSIRT issue is observed before, and if the issue is reproducecible in local per CR description.


[Next Action - to Next Module]

To EE file owner to comment the EE reason. (

dpcopro_hisr.c:)


[Analysis Result – Current Module 1]




2. The gNB is configured to send the modified RRCSetup message (with {{pdsch-AggregationFactor=n2}} in PDSCH-Config) to any connecting UE

4. The phone will perform RACH → receive the modified RRCSetup → modem ASSERT triggers within ~15 seconds







Update current status and observation from NRRC_CONFIG.

1. Currently no available log.

2. Assert is not in RRC side, it's in "*[ASSERT] dpcopro_hisr.c:811* — 1st ASSERT (p1=0, p2=0, p3=0) |" Per CR Description.

3. For the mentioned IE,  pdsch-AggregationFactor is within value range and comply with the spec limitation.

4. Check PSIRT  CR from 2024 - 2026, no similar PSIRT issue found in either CR record or Code base presents special handling in 99 for this IE.

5. Reproduce same IE handling mentioned from description using GUEST: RRC handling is pass and no assertion/fatal observed. (See below)









Conclusion from NRRC_CONFIG:

- Need assert file owner help to conclude what cause the assertion.





[Analysis Result – Current Module 2] (Optional)





[Analysis Result – Current Module 3] (Optional)





[Selected SOP](fill-in accurate "SOP name(s)", “out of SOP coverage”, “lv3/4 issue”, or “others”. For LI group please fill-in SharePoint itemlink)



[End of Selected SOP]



[Automation Suggestion]
If the analyzed issue does not have an appropriate syndrome for this module, please provide the following details.
(This feedback is primarily used for issue automation evaluation. Please consider that the previous handler RD should have the ability to select the appropriate syndrome and provide the key information.)

Proposed syndrome name:
Required info for automation: (mandatory or optional)
1.
2.

Reference link:RRC Lv3 syndromes


[End of Automation Suggestion]



[For Gen99R TC42 issue only]

[MTK internal use only]
// Select one item, delete others. Don’t modify selected item content except estimated time
//=============Check log and information=============
1. [Step A on-going] Checking CR log and enough information, asking more information/log to customer.
2.[Step A Done] Confirmed issue triage could be performed.
//=============Root cause not yet confirmed and Analysis/retest ongoing=============
3. [Step B on-going] Can not provide moduleanalysis results yet, and module analysis ongoing; estimated analysis conclusion date: 2023/xx/xx EOD (PST).
4. [Step B on-going] Retest requested, to get more debug information including filter change, releasing debug SW, test procedure change, missing log or any other reason.
5. [Step B Done] Module analysis done and move to next moduleowner or need customer feedback.
//=============Root cause not yet confirmed while workaround could be given=============
6-a-1. [Step C on-going] UE workaround/temp solution development is on-going, estimated ready to release date : 2023/xx/xx EOD (PST).
6-a-2. [Step C Done] UE workaround/temp solution released, wait for customer retest.
6-b-1. [Step C Done] Test step/configuration workaround proposed, wait for customer retest.
//=============Root cause found and Final Solution=============
6-c. [Step C Done] Root cause found; solution under discussion; estimated lock down design date: 2023/xx/xx EOD (PST).
6-d. [Step C Done] Solution implementation/verification(including debug patch verification to customer) is on-going, ETA : 2023/xx/xx EOD (PST) and fill in CR done. Please remember provide RCA
6-e. [Step C Done] Solution check-in and ETA fill in CR done. Please remember provide RCA (No need provide again if solution not change).
```

### Note 9 — 2026-03-13 14:15:45 — srv_cqsrv_hbgsm001 (srv_cqsrv_hbgsm001) — Mode: Internal Use

```
External - HackerOne Comment ID: 40016710
mtk_benjamin posted a comment:
Hi,

The MediaTek Security team has taken an initial review on this report but require additional information so as to accurately assess this report.

We’re unable to successfully reproduce the assertion for this issue on the platform you provided.
Do you have a PoC for a newer platform?

Thanks,
MediaTek Security Team
```

### Note 10 — 2026-03-13 14:15:47 — srv_cqsrv_hbgsm001 (srv_cqsrv_hbgsm001) — Mode: Internal Use

```
External - HackerOne Comment ID: 40017289
qiqingh posted a comment:
Hi,

Thank you for the update.

Regarding reproduction on our device: we performed a fresh test today (2026-03-12) and the issue is consistently reproducible on our Redmi K40 Gaming (Dimensity 1200 / MT6893, MOLY.NR15.R3.TC8.PR2.SP.V2.1.P70, SPL 2023-04-01). A single connection attempt triggered 3 cascading ASSERT failures:

|| # || CCCI_MD_MSG_EXCEPTION || [ASSERT] dpcopro_hisr.c:811 || modemCrashReasons ||
| 1 | 22:18:54.440 | 22:19:02.068 | bwp (22:19:21.929) |
| 2 | 22:19:30.928 | 22:19:36.513 | bwp (22:19:56.560) |
| 3 | 22:20:05.987 | 22:20:11.479 | bwp (22:20:31.161) |

Including today, we have reproduced this across 4 independent sessions, all with identical crash signatures. The attached {{phone_log_reproduce3.log}} contains the full adb logcat from today's session.

We also verified the PoC payload using Wireshark/tshark, which successfully decodes the {{pdsch-AggregationFactor: n2}} field from the UPER-encoded DL-CCCH-Message without any parsing errors. All three valid enum values ({{n2}}, {{n4}}, {{n8}}) trigger the same ASSERT.

Regarding a newer platform: we have tested the same PoC on a Vivo X100 (Dimensity 9300, MOLY.NR16 firmware), and the crash does not reproduce there. We do not currently have a PoC for a newer platform.

Please let us know if any additional information would be helpful.

Thanks,
Qiqing
[^F5523263_phone_log_reproduce3.log]

Attachment: [^F5523263_phone_log_reproduce3.log]
```

### Note 11 — 2026-03-23 11:47:20 — test_lone_use001 (test_lone_use001) — Mode: Internal Use

```
[codebase_label] NR15.R3.TC8.PR2.SP.W21.45.p2
```

### Note 12 — 2026-03-23 11:49:54 — srv_cap (srv_cap) — Mode: CAP_AutoProcResult_NoMail

```
ADL Report (42467024)=> \cr\prod\MOLY01839054\unzip\331802947\MSV-7865_1\MSV-7865_1\MemoryDump_2026_03_23_11_18_47.bin
ADL Report (42467037)=> \cr\prod\MOLY01839054\unzip\331803004\MSV-7865_2\MSV-7865_2\MemoryDump_2026_03_23_11_28_05.bin
```

### Note 13 — 2026-03-23 11:50:20 — srv_pf_agent001 (srv_pf_agent001) — Mode: Issue Analysis

```

Log Analysis Summary

ModuleLog PathTimestampKey LogConclusion
IPFG97_Petrus_Tempload_202603231-2.elg2130574[DPC_COPRO]DPC driver assert line:801,v0=0x0,v1=0x2,v2=0x0Gen97 excep err
IPFG97_Petrus_Tempload_202603231.elg44327750[DPC_COPRO]DPC driver assert line:801,v0=0x0,v1=0x2,v2=0x0Gen97 excep err
```

### Note 14 — 2026-03-23 11:54:47 — srv_aita001 (srv_aita001) — Mode: Internal Use

```
AITA dashboard:https://newcap.mediatek.inc/dashboard/cap-result/MOLY01839054/AITA

== AITA execution log ==
2026-03-23 11:54:42: parse G99_Jayer_R2MP_OF_Pass_20260323.elg success
2026-03-23 11:55:04: parse G97_Petrus_Tempload_202603231.elg success
2026-03-23 11:55:45: parse G97_Petrus_Tempload_202603231-2.elg fail
```

### Note 15 — 2026-03-24 10:23:14 — Eric-sr Peng (mtk31228) — Mode: Issue Analysis

```

Dear DBRP,




Please help check UPP this assert.

Log: Attach >MSV-7865_1.rar

MD load: Attach >BIN+ELF-202603181021_66677153_build563385.zip




This is UPP excpetion of TB len error. UPP ot TB end with CRC pass but didn't get any CB data.

The last three MPIF commands are:




TB_START_0   0x40000000   0x04e11140
NTX
TB len = 0x4e1
SIM1, CG0, CC0, HARQ10, TB0
TB_START_1   

0x80000200   0x02720000
CB num=2
CB len=0x272
TB_END            0x17428420   0x13871140
Real TB end
CRC pass
SIM1, CG0, CC0, HARQ10, TB0



BRs,

Eric-sr Peng
```

### Note 16 — 2026-03-24 10:40:11 — srv_ddzadmin002 (srv_ddzadmin002) — Mode: Internal Use

```

DORA (DSP Online Robot Analyst)

DORA is triggered:
http://mtkmspmoa01:8000/crloganalyzer/detail/41931

(Re-click the link after your first login)
```

### Note 17 — 2026-03-24 10:40:14 — srv_ddzadmin002 (srv_ddzadmin002) — Mode: Internal Use

```

Transfer CR to EE robot

Original Assignee: srv_dsp_nr_brp001

New Assignee: srv_dsp_irat_ee001

After DORA analysis, it will be transferred to correct owner or original assignee.
```

### Note 18 — 2026-03-24 10:54:28 — srv_ddzadmin002 (srv_ddzadmin002) — Mode: Internal Use

```

DORA (DSP Online Robot Analyst)

Status:
SUCCESS

Report Link:
http://mtkmspmoa01:8000/crloganalyzer/report/41931

(Re-click the link after your first login)

Feedback Link:
https://imtkteams.mediatek.inc/sites/CSD/MSP/Common%20Sharing/Lists/dora_feedback/EditForm.aspx?ID=23224
```

### Note 19 — 2026-03-24 12:25:10 — srv_ddzadmin002 (srv_ddzadmin002) — Mode: Internal Use

```

Transfer CR from EE robot to srv_dsp_nr_brp001

Reason: CR is pending over 1.5 hours, transfer it back to original owner
```

### Note 20 — 2026-03-24 13:37:43 — Cloudy Wu (mtk11646) — Mode: Internal Use

```

Manual Dispatch => DBRP, Yen-chieh
```

### Note 21 — 2026-03-31 14:04:16 — srv_cqsrv_hbgsm001 (srv_cqsrv_hbgsm001) — Mode: Internal Use

```
External - HackerOne Comment ID: 40385113
mtk_benjamin posted a comment:
Hi,

The MediaTek Security team has conducted an initial severity assessment on this security issue.
Based on internal assessment, it was rated as High severity.

If you have additional information that you believe we should use to reassess this report, please let us know.

Thanks,
MediaTek Security Team
```

### Note 22 — 2026-03-31 14:04:18 — srv_cqsrv_hbgsm001 (srv_cqsrv_hbgsm001) — Mode: Internal Use

```
External - HackerOne Comment ID: 40385130
mtk_benjamin posted a comment:
after internal assessment, it's be evaluated as High.
```

### Note 23 — 2026-06-28 20:03:04 — srv_cqsrv_hbgsm001 (srv_cqsrv_hbgsm001) — Mode: Internal Use

```
External - HackerOne Comment ID: 42375106
mt_miles posted a comment:
Hi,

We will be releasing a patch for this issue in a future MediaTek Product Security Bulletin.
It will first be released to our OEM partners, then to the public after two months.

Your CVE is CVE-2026-20504

We would also like to recognize your contribution on [MediaTek Product Security Acknowledgements|https://corp.mediatek.com/product-security-acknowledgements].
Based on our record, your credit information is "Qiqing Huang, Xingyu Wang, Hongxin Hu@UBSec". Please let us know if it has changed.

Thanks,
MediaTek Security Team
```

### Note 24 — 2026-06-28 20:03:06 — srv_cqsrv_hbgsm001 (srv_cqsrv_hbgsm001) — Mode: Internal Use

```
External - HackerOne Comment ID: 42392533
qiqingh posted a comment:
Hi MediaTek Security Team,

Thank you for the update.

I confirm that the credit information is correct:

Qiqing Huang, Xingyu Wang, Hongxin Hu@UBSec

Thanks,
Qiqing
```
