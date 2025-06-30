variable "aws_region" {
  description = "AWS 리전"
  default     = "ap-northeast-2"
}

variable "your_ip" {
  description = "SSH 접속을 허용할 본인 IP"
  type        = string
}

variable "ssh_public_key" {
  description = "SSH 공개 키 내용"
  type        = string
}