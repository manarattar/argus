# Northstar Manufacturing B.V. — Independent Cybersecurity Assessment

> **FICTIONAL DEMONSTRATION DOCUMENT.** Prepared for the ARGUS demonstration
> corpus. Northstar Manufacturing B.V. does not exist. The assessor named below
> is fictional.

Assessor: Kestrel Assurance B.V.
Engagement: Independent control assessment, NIS2-aligned
Fieldwork: 8 September – 3 October 2025
Report issued: 21 October 2025
Follow-up review: 6 March 2026

<!-- page: 1 -->

## 1. Engagement Summary

Kestrel Assurance was engaged by the board of Northstar Manufacturing B.V. to
perform an independent assessment of information security controls across
corporate IT and both production environments. This was the company's first
independent security assessment.

The assessment covered 14 control domains and included configuration review,
external and internal network testing, and interviews with 11 staff.

## 2. Overall Rating

Control maturity assessed at **2.9 / 5** (October 2025), against a target of 3.5
for an organisation of this profile.

Re-assessed at **3.4 / 5** at the March 2026 follow-up review.

| Domain | Oct 2025 | Mar 2026 |
|---|---|---|
| Identity and access management | 2.4 | 3.5 |
| Network segmentation | 2.1 | 3.2 |
| Endpoint protection | 3.4 | 3.8 |
| Vulnerability management | 2.6 | 3.4 |
| Logging and monitoring | 2.2 | 3.6 |
| Backup and recovery | 3.6 | 3.9 |
| Incident response | 2.0 | 3.3 |
| Third-party / supplier security | 1.9 | 2.2 |
| OT / production environment | 2.7 | 3.0 |
| Change management | 3.1 | 3.4 |
| Data protection | 3.3 | 3.5 |
| Physical security | 3.8 | 3.8 |
| Security awareness | 2.8 | 3.5 |
| Governance and policy | 2.5 | 3.4 |

## 3. Findings and Remediation Status

<!-- page: 2 -->

Twenty-three findings were raised in October 2025: 4 high, 11 medium, 8 low.

As at the March 2026 follow-up: **19 of 23 findings closed** (4 of 4 high, 10 of
11 medium, 5 of 8 low).

### 3.1 High-severity findings (all closed)

**H-01 — No multi-factor authentication on remote access.** The corporate VPN
and the Ostrava remote maintenance path both accepted single-factor
authentication. *Closed December 2025: MFA enforced on all remote access paths,
verified by re-test.*

**H-02 — Flat network between corporate IT and Ostrava production.** No
segmentation existed between the corporate network and the Ostrava OT
environment. A compromise of a corporate workstation would have provided direct
network reachability to production control systems. *Closed February 2026:
segmentation implemented and verified by re-test.*

**H-03 — Domain administrator credentials shared between four staff.** *Closed
November 2025: individual privileged accounts issued, shared account disabled,
privileged access management tooling deployed.*

**H-04 — No centralised logging; 30-day retention on isolated systems.** No
capability existed to reconstruct an incident across systems. *Closed
January 2026: centralised log aggregation deployed across corporate and OT
environments with 400-day retention.*

### 3.2 Open findings as at March 2026

<!-- page: 3 -->

**M-07 — Supplier security assessment process not established.** Northstar has
no process for assessing the security posture of suppliers with network or data
access. Eleven suppliers have some form of connectivity or data access; none has
been assessed. *Open. Target date: Q4 2026.*

**L-03 — Formal security exception register not maintained.** *Open. Target date:
Q3 2026.*

**L-06 — Removable media controls not enforced on Ostrava engineering
workstations.** *Open. Target date: Q3 2026.*

**L-08 — Security awareness training not mandatory for contractors.** *Open.
Target date: Q3 2026.*

## 4. Incident History

<!-- page: 4 -->

Northstar reported no confirmed security incidents in the 24 months preceding
the October 2025 assessment.

That statement should be read with the finding at H-04 in mind: for the majority
of that period the company lacked centralised logging and had 30-day retention
on isolated systems. Kestrel found no evidence of any incident, and equally
found that the company would have had limited capability to detect or
reconstruct one. The absence of reported incidents is therefore weak evidence of
the absence of incidents.

Since centralised logging was deployed in January 2026, the company has recorded
and closed two low-severity events (a phishing email reported by a user, and a
misconfigured firewall rule identified by monitoring). Both were handled through
the new incident response process.

## 5. Assessor's Conclusion

<!-- page: 5 -->

Northstar's security posture in October 2025 was materially below what would be
expected for a manufacturer of this size operating OT environments, with four
high-severity findings including an unsegmented path from corporate IT to
production control systems.

The remediation response has been the most effective the assessor has observed
in a first-assessment engagement of this type. All four high-severity findings
were closed within five months and verified by re-test. Overall maturity moved
from 2.9 to 3.4, and every domain improved.

The remaining exposure is concentrated in third-party security, which improved
only marginally (1.9 to 2.2) and remains the weakest domain. Given that eleven
suppliers hold connectivity or data access and none has been assessed, this is
the assessor's principal residual concern.

In the assessor's opinion, technology risk at Northstar has moved from
significantly elevated to broadly appropriate for the organisation's profile,
with one clearly identified residual gap and a credible plan to address it.
