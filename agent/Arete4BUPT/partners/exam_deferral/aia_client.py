"""
AIA (Agent Identity Authentication) 客户端
向 CA 申请 mTLS 双向证书。模拟 acme-client.sh 流程：
  acme-client.sh new-cert --agent-id <AIC>

本地实现：使用 cryptography 库生成自签 CA + Agent 证书供开发测试用。
生产环境应替换为真正的 ACME / 内部 CA 流程。
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

from atr_client import get_aic, load_config, save_config


CERTS_DIR = Path(__file__).parent / "certs"


def issue_certificates(agent_id: str = None) -> dict:
    """生成 ca.crt / agent.crt / agent.key 用于 mTLS"""
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
    except ImportError:
        print("[AIA] ⚠ 缺少 cryptography 库，请运行: pip install cryptography")
        return {}

    aic = get_aic()
    if not aic:
        print("[AIA] ⚠ 未发现 AIC，请先运行 python atr_client.py 完成 ATR 注册")
        return {}

    agent_id = agent_id or "deferred-exam-partner"
    CERTS_DIR.mkdir(exist_ok=True)

    print(f"[AIA] 正在为 Agent {agent_id} (AIC={aic}) 申请 mTLS 证书...")

    # 1) 生成 CA 私钥 + CA 证书 (自签)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_subject = ca_issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ACP-Training-CA"),
        x509.NameAttribute(NameOID.COMMON_NAME, "ACP Internal CA"),
    ])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_subject)
        .issuer_name(ca_issuer)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )

    # 2) 生成 Agent 私钥 + Agent 证书 (由 CA 签发)
    agent_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    agent_subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ACP-Training-Camp"),
        x509.NameAttribute(NameOID.COMMON_NAME, f"{agent_id}.{aic}"),
    ])
    agent_cert = (
        x509.CertificateBuilder()
        .subject_name(agent_subject)
        .issuer_name(ca_subject)
        .public_key(agent_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=90))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.DNSName(agent_id),
            ]),
            critical=False,
        )
        .add_extension(
            x509.ExtendedKeyUsage([
                x509.oid.ExtendedKeyUsageOID.SERVER_AUTH,
                x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH,
            ]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    # 3) 写入文件
    ca_path = CERTS_DIR / "ca.crt"
    cert_path = CERTS_DIR / "agent.crt"
    key_path = CERTS_DIR / "agent.key"

    ca_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    cert_path.write_bytes(agent_cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(agent_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ))

    # 4) 更新 config.toml 中证书路径
    config = load_config()
    config["tls"]["cert_path"] = str(cert_path.relative_to(Path(__file__).parent))
    config["tls"]["key_path"] = str(key_path.relative_to(Path(__file__).parent))
    config["tls"]["ca_path"] = str(ca_path.relative_to(Path(__file__).parent))
    save_config(config)

    print(f"[AIA] ✓ CA 证书:    {ca_path}")
    print(f"[AIA] ✓ Agent 证书: {cert_path}")
    print(f"[AIA] ✓ Agent 私钥: {key_path}")
    print(f"[AIA] ✓ config.toml 中证书路径已更新")
    print(f"[AIA] ✓ 有效期: 90 天")

    return {
        "ca": str(ca_path),
        "cert": str(cert_path),
        "key": str(key_path),
    }


if __name__ == "__main__":
    result = issue_certificates()
    sys.exit(0 if result else 1)
