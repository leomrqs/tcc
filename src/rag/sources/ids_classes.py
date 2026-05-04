"""
Base de conhecimento curada: descrições canônicas das classes de ataque
dos datasets CIC-IDS2017 e UNSW-NB15.

Cada documento descreve uma categoria de ataque com:
- Definição operacional
- Características de fluxo de rede típicas (FORMA, TAXA, DURAÇÃO)
- Padrões de flags TCP / estado UNSW
- Subtipos comuns
- MITRE ATT&CK techniques associadas
- Exemplos de ferramentas

A semântica é alinhada com o text_converter v2 (mesmas categorias FLOOD/HIGH/etc.),
fazendo com que a busca por similaridade tenha alto recall.
"""

from src.utils.logger import get_logger

logger = get_logger(__name__)


# ════════════════════════════════════════════════════════════════
# Descrições canônicas (15 categorias unificadas)
# ════════════════════════════════════════════════════════════════

CLASS_DESCRIPTIONS = [
    # ─────────────────────────────────────────────────────────────
    {
        "id": "CLASS-BENIGN",
        "title": "Benign — Tráfego de Rede Legítimo",
        "text": """Benign / Normal traffic represents legitimate network communication from regular users and applications.

NETWORK FLOW SIGNATURE:
- FORMA DO FLUXO: SIMÉTRICO (bidirectional dialog, balanced fwd/bwd ratio between 0.1 and 10)
- TAXA DE PACOTES: MODERADA (1-100 pkt/s typical for application traffic)
- TAXA DE BYTES: MODERADA to ALTA (10KB/s to 1MB/s for normal apps)
- DURAÇÃO: MEDIUM (0.5s to 5min for HTTP/HTTPS, longer for streaming/SSH)
- PAYLOAD: present in both directions, real data
- PROTOCOLS: HTTP (80/8080), HTTPS (443/8443), DNS (53), SSH (22), SMTP (25), IMAP (143), standard ports
- TCP FLAGS: SYN+ACK+PSH+FIN (full handshake, data transfer, normal termination)
- STATE (UNSW): FIN, CON, ACC — connection completed normally

COMMON PATTERNS:
- Web browsing: short HTTPS sessions, symmetric, multiple parallel connections
- Email: SMTP/IMAP with persistent control + bursts of data
- DNS: small UDP, request-response, sub-second
- SSH: long-lived TCP, encrypted, low rate, symmetric
- Video streaming: sustained download-heavy, high byte rate, long duration

DISTINGUISHING FROM ATTACKS:
- Has actual response from destination (not unidirectional)
- Rate is not abnormally high (not FLOOD)
- Doesn't repeat identical patterns from same source (not scan)
- Uses recognized service ports
- Connection state shows successful negotiation

MITRE: (none — benign traffic, no technique)""",
        "metadata": {"category": "Benign", "source_type": "ids_class"},
    },
    # ─────────────────────────────────────────────────────────────
    {
        "id": "CLASS-DOS",
        "title": "DoS — Denial of Service Attack",
        "text": """Denial of Service (DoS) attacks aim to make a service unavailable by exhausting resources from a single source.

NETWORK FLOW SIGNATURE:
- FORMA DO FLUXO: UNIDIRECIONAL (no response) or HALF-OPEN (incomplete handshake)
- TAXA DE PACOTES: ALTA (100-1000 pkt/s for a single source)
- DURAÇÃO: LONG to VERY LONG (sustained attack over minutes/hours)
- PAYLOAD: small or zero (control packets only)
- TARGET: typically port 80 (HTTP), 443 (HTTPS), application services

DOS SUBTYPES IN CIC-IDS2017:
- DoS Slowloris: very LOW rate but sustained, holds connections open with partial HTTP requests
  → DURAÇÃO: VERY LONG, TAXA: BAIXA, FORMA: UNIDIRECIONAL on HTTP
- DoS Slowhttptest: similar to Slowloris, slow body POST
  → Long-lived HTTP POST that never completes
- DoS Hulk: ALTA rate of HTTP requests with random query parameters
  → ALTA pkt/s, SHORT individual flows but many parallel
- DoS GoldenEye: HTTP request flood with Keep-Alive abuse
  → Sustained ALTA rate per connection
- Heartbleed: Memory leak via malformed TLS heartbeat
  → SHORT duration, abnormal HTTPS flow shape

DISTINGUISHING FROM DDoS:
- DoS comes from ONE source IP (single attacker)
- DDoS comes from MANY sources simultaneously
- DoS often uses application-layer techniques (slow attacks)
- DDoS is volumetric, network-layer (SYN flood, UDP flood)

DISTINGUISHING FROM Reconnaissance:
- DoS sustains the attack (LONG duration, ALTA rate sustained)
- Reconnaissance probes briefly and moves on (SHORT, low repeat per target)

MITRE TECHNIQUES: T1499 (Endpoint Denial of Service), T1499.002 (Service Exhaustion Flood),
T1499.003 (Application Exhaustion Flood), T1499.004 (Application or System Exploitation)""",
        "metadata": {"category": "DoS", "source_type": "ids_class"},
    },
    # ─────────────────────────────────────────────────────────────
    {
        "id": "CLASS-DDOS",
        "title": "DDoS — Distributed Denial of Service",
        "text": """Distributed Denial of Service (DDoS) is a volumetric attack from many compromised hosts (botnet) targeting one victim.

NETWORK FLOW SIGNATURE (per individual flow from one bot):
- FORMA DO FLUXO: UNIDIRECIONAL (overwhelm, no need to wait response)
- TAXA DE PACOTES: FLOOD (>1000 pkt/s aggregate, individual flows can be SHORT bursts)
- TAXA DE BYTES: FLOOD (>10MB/s aggregate)
- DURAÇÃO: SHORT individual flows, sustained as a campaign
- PAYLOAD: typically minimal (just enough to trigger server processing)
- TCP FLAGS: SYN-only spam (SYN flood) or PSH+ACK floods
- HEAVY REPETITION: multiple identical/similar flows from many sources

DDoS SUBTYPES:
- SYN Flood: TAXA FLOOD of SYN packets, target's connection table exhausted
  → FLAGS: SYN=N, ACK=0, FIN=0; FORMA: UNIDIRECIONAL
- UDP Flood: random UDP packets to random ports
  → No flags (UDP), FORMA: UNIDIRECIONAL, MODERADA-ALTA per flow
- ICMP Flood: ping flood
- LOIC/HOIC: HTTP GET flood at application layer
  → ALTA rate of HTTP requests
- Amplification (DNS, NTP, Memcached): small request, huge reply
  → DOWNLOAD shape, ALTA byte rate from server

DISTINGUISHING FROM DoS:
- Aggregate FLOOD rate vs ALTA rate
- DDoS shows multiple source addresses converging on same target
- DDoS individual flow can look like simple probe; aggregate reveals attack

DISTINGUISHING FROM Reconnaissance:
- Reconnaissance is INFORMATION GATHERING (low volume)
- DDoS is RESOURCE EXHAUSTION (high volume)

MITRE TECHNIQUES: T1498 (Network Denial of Service), T1498.001 (Direct Network Flood),
T1498.002 (Reflection Amplification)""",
        "metadata": {"category": "DDoS", "source_type": "ids_class"},
    },
    # ─────────────────────────────────────────────────────────────
    {
        "id": "CLASS-BRUTEFORCE",
        "title": "Brute Force — Credential Attack (SSH/FTP/Web)",
        "text": """Brute Force attacks attempt many username/password combinations against an authentication service.

NETWORK FLOW SIGNATURE:
- FORMA DO FLUXO: SIMÉTRICO (each attempt requires server response)
- TAXA DE PACOTES: ALTA (multiple attempts per second)
- DURAÇÃO: each individual login attempt is SHORT (0.1s-3s), but campaign is LONG
- PAYLOAD: present (sending credentials)
- TCP FLAGS: SYN+ACK+PSH+FIN per attempt (full session, then close)
- HEAVY REPETITION: multiple short flows to SAME destination port from same source
- "CONEXÕES PRÉVIAS no mesmo state/TTL" should be HIGH (5+)

BRUTE FORCE SUBTYPES IN CIC-IDS2017:
- FTP-Patator: brute force against FTP login (port 21)
  → Service: FTP, SHORT flows, PSH flag, CONEXÕES PRÉVIAS: high
- SSH-Patator: brute force against SSH login (port 22)
  → Service: SSH, SHORT flows, encrypted payload
- Web Attack — Brute Force: HTTP POST credential stuffing on web forms
  → Service: HTTP, POST requests with credentials in body

DISTINGUISHING FROM Reconnaissance:
- Brute Force is SIMÉTRICO (server responds to each attempt with auth failure)
- Reconnaissance is UNIDIRECIONAL or HALF-OPEN (just probing presence)
- Brute Force has actual payload (credentials)
- Brute Force connects to known auth ports (22, 21, 80/443 forms)

DISTINGUISHING FROM Benign:
- Excessive repetition from same source
- Almost all attempts fail (RST or auth failure response)
- Higher rate than human user could possibly type

MITRE TECHNIQUES: T1110 (Brute Force), T1110.001 (Password Guessing),
T1110.003 (Password Spraying), T1110.004 (Credential Stuffing)""",
        "metadata": {"category": "Brute Force", "source_type": "ids_class"},
    },
    # ─────────────────────────────────────────────────────────────
    {
        "id": "CLASS-BOTNET",
        "title": "Botnet — Command & Control Communication",
        "text": """Botnet traffic is communication between compromised hosts (bots) and Command & Control (C2) servers.

NETWORK FLOW SIGNATURE:
- FORMA DO FLUXO: SIMÉTRICO but with low data volume (control messages)
- TAXA DE PACOTES: BAIXA to MODERADA (beaconing pattern)
- DURAÇÃO: LONG to VERY LONG (persistent connections) or PERIODIC short bursts
- PAYLOAD: small, encrypted, often HTTPS or DNS tunneling
- PORTS: often non-standard (high ports), or HTTP/HTTPS to disguise
- BEACONING: regular intervals (e.g., flow every 60s, every 5min)
- DOMAIN GENERATION ALGORITHMS (DGA): connections to algorithmically-generated domains

BOTNET SUBTYPES IN DATASETS:
- ARES (CIC): commodity botnet using HTTP-based C2
  → HTTP traffic to non-standard endpoints, periodic check-ins
- IRC bots: classic C2 over IRC (port 6667)
- Generic HTTP bots: HTTPS to suspicious domains, low volume

DISTINGUISHING FROM Benign:
- Connections to unknown/suspicious destinations
- Periodic/regular intervals (beacons) — unlike user-driven traffic
- Low data volume disguised in long sessions
- DNS queries to algorithmically-generated names

DISTINGUISHING FROM Backdoor:
- Botnet is CALL-OUT (bot calls home to C2)
- Backdoor is LISTENING (attacker connects to compromised host)

MITRE TECHNIQUES: T1071 (Application Layer Protocol), T1071.001 (Web Protocols),
T1071.004 (DNS), T1095 (Non-Application Layer Protocol), T1568.002 (Domain Generation Algorithms),
T1029 (Scheduled Transfer)""",
        "metadata": {"category": "Botnet", "source_type": "ids_class"},
    },
    # ─────────────────────────────────────────────────────────────
    {
        "id": "CLASS-RECON",
        "title": "Reconnaissance — Network Scanning and Probing",
        "text": """Reconnaissance is the discovery phase: identifying live hosts, open ports, services, and vulnerabilities.

NETWORK FLOW SIGNATURE:
- FORMA DO FLUXO: HANDSHAKE-ONLY (no payload) or UNIDIRECIONAL (no response from closed ports)
- TAXA DE PACOTES: BAIXA per individual probe, but MANY probes total
- DURAÇÃO: INSTANT (single packet) to SHORT (TCP handshake attempts)
- PAYLOAD: zero or minimal (probe packets)
- TCP FLAGS: SYN-only (SYN scan), or NULL/FIN/XMAS for stealth scans, or full SYN+ACK+RST
- VOLUME: 1-3 packets per flow, but to MANY destinations or ports
- STATE (UNSW): REQ (request only), RST (rejection)

RECONNAISSANCE SUBTYPES:
- PortScan (CIC): TCP/UDP probes to enumerate open ports on target
  → Single SYN per port, no response from closed ports
- Nmap-style scans: SYN, FIN, NULL, XMAS scans
- Sweep scans: sequential IPs, single port (find live hosts)
- Service version detection: short banner-grab connections
- Vulnerability scanning: probes specific CVEs (Nessus, OpenVAS)

UNSW-NB15 RECONNAISSANCE:
- Pre-attack info gathering
- Service enumeration
- OS fingerprinting via TTL/window analysis

DISTINGUISHING FROM DoS:
- Reconnaissance: BAIXA volume, MANY targets (one probe each)
- DoS: ALTA-FLOOD volume, ONE target (sustained attack)

DISTINGUISHING FROM Brute Force:
- Reconnaissance: HANDSHAKE-ONLY or UNIDIRECIONAL, no auth attempts
- Brute Force: SIMÉTRICO with credential payload

DISTINGUISHING FROM Benign:
- No real payload (just probes)
- Pattern of repeated attempts to many ports/hosts
- Many failed/rejected handshakes

MITRE TECHNIQUES: T1046 (Network Service Scanning), T1595 (Active Scanning),
T1595.001 (Scanning IP Blocks), T1595.002 (Vulnerability Scanning), T1018 (Remote System Discovery)""",
        "metadata": {"category": "Reconnaissance", "source_type": "ids_class"},
    },
    # ─────────────────────────────────────────────────────────────
    {
        "id": "CLASS-WEBATTACK",
        "title": "Web Attack — SQL Injection, XSS, Web Exploits",
        "text": """Web Attacks target web applications via HTTP/HTTPS — exploiting input validation flaws.

NETWORK FLOW SIGNATURE:
- FORMA DO FLUXO: SIMÉTRICO (request + response)
- TAXA DE PACOTES: MODERADA (HTTP request rate, not flood)
- DURAÇÃO: SHORT (single request) to MEDIUM (browsing session)
- PAYLOAD: HTTP requests with malicious query strings or POST bodies
- PORTS: 80, 443, 8080, 8443
- TCP FLAGS: SYN+ACK+PSH+FIN (normal HTTP), but content is malicious
- VOLUME: typically 1 request per attack, but exploit campaigns repeat

WEB ATTACK SUBTYPES IN CIC-IDS2017:
- SQL Injection: malicious SQL in URL parameters or POST body
  → Detection at network layer is hard; flow looks like normal HTTP
  → Look for: long unusual query strings, SQL keywords in payload (UNION, SELECT, ', --)
- XSS (Cross-Site Scripting): JavaScript injection in form fields
  → Look for: <script>, javascript:, onerror= in payload
- Web Brute Force (covered separately): credential stuffing on login forms

DISTINGUISHING FROM Benign HTTP:
- Network-level features alone are insufficient
- Payload analysis (DPI) is needed for accurate detection
- Look for unusual response codes (500, 403 for blocked attacks)
- Repeated attempts from same source against /admin, /login, /wp-login

MITRE TECHNIQUES: T1190 (Exploit Public-Facing Application), T1059.007 (JavaScript),
T1210 (Exploitation of Remote Services)""",
        "metadata": {"category": "Web Attack", "source_type": "ids_class"},
    },
    # ─────────────────────────────────────────────────────────────
    {
        "id": "CLASS-EXPLOITS",
        "title": "Exploits — Vulnerability Exploitation",
        "text": """Exploits target known vulnerabilities (CVEs) in network services or applications to gain unauthorized access.

NETWORK FLOW SIGNATURE:
- FORMA DO FLUXO: variable (often UNIDIRECIONAL for buffer overflow shellcode delivery)
- TAXA DE PACOTES: BAIXA (single exploit attempt) to MODERADA
- DURAÇÃO: INSTANT to SHORT (exploits are typically fast)
- PAYLOAD: often LARGE (shellcode, RCE payload) or VERY SPECIFIC pattern
- PORTS: targeted service ports (445 SMB, 22 SSH, 3389 RDP, application ports)
- ANOMALOUS: malformed packets, unusual TCP options, oversized fields

EXPLOIT SUBTYPES IN UNSW-NB15:
- Browser exploits: targeting client browsers
- Server software exploits: SMB (EternalBlue), RDP (BlueKeep), Apache, IIS
- Buffer overflows
- CVE-specific payloads (e.g., CVE-2017-0144 EternalBlue)

EXPLOIT SUBTYPES IN CIC-IDS2017:
- Heartbleed: TLS heartbeat memory leak
  → Specific malformed TLS heartbeat payload
- Infiltration: compromised host pivots laterally (more lateral than exploit)

DISTINGUISHING FROM Reconnaissance:
- Reconnaissance: probes multiple targets, no payload delivery
- Exploits: targets specific vulnerable service with weaponized payload

DISTINGUISHING FROM Brute Force:
- Brute Force: tries credentials repeatedly (legitimate auth protocol use)
- Exploits: sends crafted malicious payloads to trigger vulnerabilities

DISTINGUISHING FROM Fuzzers:
- Exploits: targeted, deliberate, weaponized payload for known CVE
- Fuzzers: random/semi-random inputs to FIND new vulnerabilities

MITRE TECHNIQUES: T1190 (Exploit Public-Facing App), T1210 (Exploitation of Remote Services),
T1212 (Exploitation for Credential Access), T1068 (Exploitation for Privilege Escalation)""",
        "metadata": {"category": "Exploits", "source_type": "ids_class"},
    },
    # ─────────────────────────────────────────────────────────────
    {
        "id": "CLASS-FUZZERS",
        "title": "Fuzzers — Automated Input Testing for Vulnerabilities",
        "text": """Fuzzers send malformed, unexpected, or random input to network services to trigger crashes and discover vulnerabilities.

NETWORK FLOW SIGNATURE:
- FORMA DO FLUXO: variable, often UNIDIRECIONAL (target crashes before responding)
- TAXA DE PACOTES: ALTA (rapid testing of many inputs)
- DURAÇÃO: SHORT individual flows, LONG campaign
- PAYLOAD: malformed, oversized, unusual encoding, edge cases
- TARGET: any service — common targets are HTTP, FTP, custom protocols
- ANOMALY: unusual packet sizes, abnormal field values, protocol violations

FUZZER CHARACTERISTICS IN UNSW-NB15:
- High volume of malformed packets
- Often causes RST responses (target rejects malformed input)
- Random or pseudo-random byte patterns
- Different from exploits because they DON'T target specific known CVE

DISTINGUISHING FROM Exploits:
- Fuzzers: random/automated input, exploring for crashes
- Exploits: targeted, deliberate weaponized payload

DISTINGUISHING FROM DoS:
- Fuzzers: VARYING payloads (testing inputs)
- DoS: REPEATING same/similar packets (volumetric)

DISTINGUISHING FROM Reconnaissance:
- Reconnaissance: discovers what's there
- Fuzzers: tests if what's there can be broken

MITRE TECHNIQUES: T1190 (Exploit Public-Facing App), T1199 (Trusted Relationship),
T1133 (External Remote Services)""",
        "metadata": {"category": "Fuzzers", "source_type": "ids_class"},
    },
    # ─────────────────────────────────────────────────────────────
    {
        "id": "CLASS-BACKDOOR",
        "title": "Backdoor — Persistent Unauthorized Access",
        "text": """Backdoors are unauthorized access mechanisms installed on compromised systems for persistent control.

NETWORK FLOW SIGNATURE:
- FORMA DO FLUXO: SIMÉTRICO with attacker-driven traffic; often LISTENING port
- TAXA DE PACOTES: BAIXA to MODERADA (interactive shell or scheduled tasks)
- DURAÇÃO: LONG (persistent connections) or PERIODIC (callbacks)
- PAYLOAD: encrypted shell commands, file transfers
- PORTS: often non-standard, sometimes hidden in HTTPS or DNS
- DIRECTION: can be REVERSE (compromised host calls out — like botnet)
              or LISTENING (attacker connects in — like backdoor proper)

BACKDOOR SUBTYPES IN UNSW-NB15:
- Reverse shells (commonly via Netcat, /dev/tcp, Metasploit Meterpreter)
- Web shells (HTTP-based, accessed via browser)
- RAT (Remote Access Trojan): persistent control with GUI
- Custom protocols on uncommon ports

DISTINGUISHING FROM Botnet:
- Backdoor: targeted at specific compromised system, attacker-controlled
- Botnet: many bots auto-controlled by C2

DISTINGUISHING FROM Benign Remote Access:
- Backdoor: uses non-standard ports/protocols, no authentication or hidden auth
- Legitimate: SSH/RDP on standard ports with known keys

MITRE TECHNIQUES: T1505 (Server Software Component), T1505.003 (Web Shell),
T1219 (Remote Access Software), T1059 (Command and Scripting Interpreter),
T1571 (Non-Standard Port)""",
        "metadata": {"category": "Backdoor", "source_type": "ids_class"},
    },
    # ─────────────────────────────────────────────────────────────
    {
        "id": "CLASS-GENERIC",
        "title": "Generic — Cipher Block Attacks (Generic UNSW class)",
        "text": """Generic in UNSW-NB15 refers to cipher attacks that work against ANY block cipher (without knowing structure).

NETWORK FLOW SIGNATURE:
- FORMA DO FLUXO: variable
- DURAÇÃO: SHORT to MEDIUM
- PAYLOAD: encrypted/malformed crypto operations
- TARGET: TLS/SSL services, encrypted protocols
- BEHAVIOR: unusual patterns in encrypted streams, possibly downgrade attacks

ALSO USED FOR:
- Generic exfiltration via standard protocols (FTP, HTTP)
- Catch-all for non-specific attack patterns
- Often misclassified due to ambiguity

DISTINGUISHING FROM Exploits:
- Exploits: specific CVE targeting
- Generic: general crypto/protocol abuse

DISTINGUISHING FROM Benign:
- Unusual cipher usage patterns
- Repeated handshake failures
- Anomalous certificate behavior

MITRE TECHNIQUES: T1573 (Encrypted Channel), T1041 (Exfiltration Over C2),
T1048 (Exfiltration Over Alternative Protocol)""",
        "metadata": {"category": "Generic", "source_type": "ids_class"},
    },
    # ─────────────────────────────────────────────────────────────
    {
        "id": "CLASS-ANALYSIS",
        "title": "Analysis — Port Analysis and Spam (UNSW class)",
        "text": """Analysis in UNSW-NB15 includes port scanning, spam, and HTML file penetrations — a broad category.

NETWORK FLOW SIGNATURE:
- FORMA DO FLUXO: variable, often HANDSHAKE-ONLY or UNIDIRECIONAL
- TAXA DE PACOTES: BAIXA to MODERADA
- DURAÇÃO: SHORT (probes) to MEDIUM
- TARGET: web services, mail, miscellaneous

ANALYSIS SUBTYPES:
- Port analysis: similar to Reconnaissance but more focused
- Spam: bulk email distribution
- HTML file penetration: exploiting browser handling of malformed HTML

DISTINGUISHING FROM Reconnaissance:
- Analysis is broader, includes content inspection and spam
- Reconnaissance is purely about discovering presence/services

MITRE TECHNIQUES: T1566 (Phishing), T1593 (Search Open Websites/Domains),
T1595 (Active Scanning)""",
        "metadata": {"category": "Analysis", "source_type": "ids_class"},
    },
    # ─────────────────────────────────────────────────────────────
    {
        "id": "CLASS-SHELLCODE",
        "title": "Shellcode — Memory Injection Payloads",
        "text": """Shellcode is small executable code injected via exploit to give attacker control (a shell).

NETWORK FLOW SIGNATURE:
- FORMA DO FLUXO: UNIDIRECIONAL (payload delivery) followed by reverse connection
- TAXA DE PACOTES: BAIXA (single delivery) plus ongoing shell session
- DURAÇÃO: INSTANT delivery + LONG follow-on session
- PAYLOAD: small (typical shellcode is <500 bytes), high entropy
- TARGET: services with RCE vulnerabilities (port 445 SMB, web servers)

SHELLCODE CHARACTERISTICS:
- High entropy in payload (machine code, often XOR-encoded)
- NOP sleds (sequences of 0x90 bytes — x86 NOP)
- Calls to specific syscalls (execve, /bin/sh)
- Reverse TCP shellcode connects back to attacker

DISTINGUISHING FROM Exploits:
- Shellcode: the PAYLOAD that runs after exploitation
- Exploits: the technique to deliver/trigger shellcode
- Together they're often classified separately, but related

MITRE TECHNIQUES: T1055 (Process Injection), T1055.001 (DLL Injection),
T1055.002 (Portable Executable Injection), T1059 (Command and Scripting Interpreter)""",
        "metadata": {"category": "Shellcode", "source_type": "ids_class"},
    },
    # ─────────────────────────────────────────────────────────────
    {
        "id": "CLASS-WORMS",
        "title": "Worms — Self-Replicating Network Malware",
        "text": """Worms are self-replicating malware that spreads automatically across networks via vulnerabilities.

NETWORK FLOW SIGNATURE:
- FORMA DO FLUXO: many UNIDIRECIONAL outbound connections from infected host
- TAXA DE PACOTES: ALTA (rapid scanning + exploitation)
- DURAÇÃO: SHORT each, but rapidly repeating
- PAYLOAD: includes worm code (binary)
- TARGET: vulnerability-specific (e.g., SMB for WannaCry, RDP for BlueKeep wormable)
- BEHAVIOR: scan + exploit + replicate pattern

WORM CHARACTERISTICS:
- Outbound connection bursts to many random IPs
- Same payload delivered to multiple targets
- Often targets worm-friendly vulnerabilities (Conficker, WannaCry, NotPetya)

DISTINGUISHING FROM Reconnaissance:
- Reconnaissance: just probes, no payload delivery
- Worms: combines scan + exploit + payload delivery

DISTINGUISHING FROM Botnet:
- Worms: SELF-PROPAGATING (no human control needed)
- Botnet: centrally controlled by attacker

MITRE TECHNIQUES: T1210 (Exploitation of Remote Services), T1021 (Remote Services),
T1080 (Taint Shared Content), T1570 (Lateral Tool Transfer)""",
        "metadata": {"category": "Worms", "source_type": "ids_class"},
    },
    # ─────────────────────────────────────────────────────────────
    {
        "id": "CLASS-INFILTRATION",
        "title": "Infiltration — Insider Compromise & Lateral Movement",
        "text": """Infiltration in CIC-IDS2017 represents post-compromise lateral movement using legitimate credentials/tools.

NETWORK FLOW SIGNATURE:
- FORMA DO FLUXO: SIMÉTRICO (looks like normal admin traffic)
- TAXA DE PACOTES: MODERADA
- DURAÇÃO: MEDIUM to LONG (interactive sessions)
- PAYLOAD: command and control, file exfiltration mixed in
- TARGET: internal network resources, file shares, databases
- ANOMALY: traffic from unusual internal source, off-hours activity

INFILTRATION CHARACTERISTICS:
- Legitimate protocols (SMB, RDP, SSH) used maliciously
- Hard to distinguish from regular admin work at network level
- Often involves data staging and exfiltration over multiple sessions
- May include privilege escalation attempts

DISTINGUISHING FROM Exploits:
- Exploits: initial access via vulnerability
- Infiltration: post-access movement using stolen credentials

DISTINGUISHING FROM Backdoor:
- Backdoor: tool installed for persistence
- Infiltration: active operations using legitimate access

MITRE TECHNIQUES: T1078 (Valid Accounts), T1021 (Remote Services), T1021.001 (RDP),
T1021.002 (SMB/Windows Admin Shares), T1570 (Lateral Tool Transfer), T1041 (Exfiltration Over C2)""",
        "metadata": {"category": "Infiltration", "source_type": "ids_class"},
    },
    # ─────────────────────────────────────────────────────────────
    # Documentos auxiliares com taxonomia comparativa
    {
        "id": "TAXONOMY-FLOW-PATTERNS",
        "title": "Network Flow Pattern Taxonomy — Quick Decision Reference",
        "text": """Quick reference for mapping network flow categorical labels to attack types:

# By FORMA DO FLUXO:
- SIMÉTRICO + SHORT + payload + standard service → Benign
- SIMÉTRICO + repeated + auth port (22/21/80) → Brute Force
- SIMÉTRICO + LONG + low rate + non-standard port → Botnet / Backdoor
- SIMÉTRICO + LONG + admin protocol (SMB/RDP) → Infiltration
- UNIDIRECIONAL + INSTANT + 1 packet → Reconnaissance (single probe)
- UNIDIRECIONAL + LONG + ALTA rate → DoS (sustained attack, no response)
- UNIDIRECIONAL + FLOOD rate → DDoS (volumetric)
- UNIDIRECIONAL + crafted payload → Exploits / Shellcode
- HANDSHAKE-ONLY + many destinations → Reconnaissance (port scan)
- EXFILTRAÇÃO + sustained → Generic / Infiltration (data theft)

# By TAXA DE PACOTES:
- FLOOD (>1000 pkt/s) → DDoS
- ALTA (100-1000) + sustained → DoS or Brute Force or Worms
- ALTA + brief → exploit attempt or aggressive scan
- MODERADA (10-100) → likely Benign or normal app traffic
- BAIXA (1-10) → Reconnaissance, Botnet beaconing, or idle Benign
- QUASE ZERO → stuck connection, stealth scan, or beaconing

# By DURAÇÃO:
- INSTANT (<10ms) → single-shot probe or exploit delivery
- SHORT (<1s) → handshake, brief query, or quick attack
- MEDIUM (1s-1min) → typical app session
- LONG (1min-10min) → SSH session, persistent connection, slow attack
- VERY LONG (>10min) → Botnet C2 persistence, idle TCP, slow DoS

# Decision tree:
1. Is rate FLOOD? → DDoS
2. Is rate ALTA + duration LONG + UNIDIRECIONAL? → DoS
3. Is duration LONG + rate BAIXA + SIMÉTRICO + non-standard port? → Botnet
4. Is shape HANDSHAKE-ONLY or UNIDIRECIONAL + INSTANT? → Reconnaissance
5. Is shape SIMÉTRICO + repeated to auth port? → Brute Force
6. Is shape EXFILTRAÇÃO + sustained? → Generic / data theft
7. Is shape SIMÉTRICO + MODERADA + standard service + has payload? → Benign
8. Otherwise: examine payload anomalies, default to Generic if uncertain.""",
        "metadata": {"category": "Taxonomy", "source_type": "ids_class"},
    },
]


def parse_ids_classes() -> list[dict]:
    """
    Retorna a base de conhecimento curada como lista de documentos
    no formato esperado pelo pipeline RAG.
    """
    documents = []
    for cls in CLASS_DESCRIPTIONS:
        documents.append({
            "id": cls["id"],
            "title": cls["title"],
            "text": cls["text"],
            "metadata": {
                **cls["metadata"],
                "title": cls["title"],
                "source": "ids_classes",
            },
            "source": "ids_classes",
        })
    logger.info(f"  IDS Classes: {len(documents)} documentos canônicos")
    return documents
