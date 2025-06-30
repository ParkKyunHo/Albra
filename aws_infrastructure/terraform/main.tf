# AWS Provider 설정
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# 기본 VPC 사용
data "aws_vpc" "default" {
  default = true
}

# SSH 키 페어
resource "aws_key_pair" "trading_key" {
  key_name   = "trading-bot-key"
  public_key = var.ssh_public_key
}

# 보안 그룹
resource "aws_security_group" "trading_sg" {
  name        = "trading-bot-sg"
  description = "Security group for trading bot"
  vpc_id      = data.aws_vpc.default.id

  # SSH (본인 IP만)
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["${var.your_ip}/32"]
  }

  # 웹 대시보드
  ingress {
    from_port   = 5000
    to_port     = 5000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # 아웃바운드
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "trading-bot-sg"
  }
}

# EC2 인스턴스
resource "aws_instance" "trading_bot" {
  ami           = "ami-0c9c942bd7bf113a2"  # Ubuntu 22.04
  instance_type = "t3.micro"
  
  vpc_security_group_ids = [aws_security_group.trading_sg.id]
  key_name               = aws_key_pair.trading_key.key_name
  
  root_block_device {
    volume_size = 20
    volume_type = "gp3"
  }

  user_data = <<-EOF
    #!/bin/bash
    apt-get update
    apt-get install -y python3-pip python3-venv git htop
    useradd -m -s /bin/bash tradingbot
    mkdir -p /home/tradingbot/app
    chown -R tradingbot:tradingbot /home/tradingbot
  EOF

  tags = {
    Name = "trading-bot-instance"
  }
}

# Elastic IP
resource "aws_eip" "trading_eip" {
  instance = aws_instance.trading_bot.id
  domain   = "vpc"

  tags = {
    Name = "trading-bot-eip"
  }
}

# S3 버킷
resource "aws_s3_bucket" "trading_backup" {
  bucket = "trading-bot-backup-${data.aws_caller_identity.current.account_id}"

  tags = {
    Name = "trading-bot-backup"
  }
}

# 계정 ID
data "aws_caller_identity" "current" {}

# 출력값
output "instance_public_ip" {
  value = aws_eip.trading_eip.public_ip
}

output "ssh_command" {
  value = "ssh -i %USERPROFILE%\\.ssh\\trading-bot-key ubuntu@${aws_eip.trading_eip.public_ip}"
}

output "s3_bucket_name" {
  value = aws_s3_bucket.trading_backup.id
}