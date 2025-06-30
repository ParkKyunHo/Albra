import boto3
import os
from datetime import datetime, timedelta

def lambda_handler(event, context):
    """일일 백업 Lambda 함수"""
    
    ec2 = boto3.client('ec2')
    s3 = boto3.client('s3')
    rds = boto3.client('rds')
    
    # 환경 변수
    instance_id = os.environ['INSTANCE_ID']
    db_instance_id = os.environ['DB_INSTANCE_ID']
    bucket_name = os.environ['BACKUP_BUCKET']
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    try:
        # 1. EC2 스냅샷 생성
        volumes = ec2.describe_volumes(
            Filters=[
                {'Name': 'attachment.instance-id', 'Values': [instance_id]}
            ]
        )
        
        for volume in volumes['Volumes']:
            snapshot = ec2.create_snapshot(
                VolumeId=volume['VolumeId'],
                Description=f'Trading Bot Backup - {timestamp}'
            )
            
            # 태그 추가
            ec2.create_tags(
                Resources=[snapshot['SnapshotId']],
                Tags=[
                    {'Key': 'Name', 'Value': f'trading-bot-backup-{timestamp}'},
                    {'Key': 'AutoDelete', 'Value': 'true'}
                ]
            )
        
        # 2. RDS 스냅샷 생성
        rds.create_db_snapshot(
            DBSnapshotIdentifier=f'trading-bot-db-backup-{timestamp}',
            DBInstanceIdentifier=db_instance_id
        )
        
        # 3. 오래된 스냅샷 삭제 (7일 이상)
        cutoff_date = datetime.now() - timedelta(days=7)
        
        # EC2 스냅샷
        snapshots = ec2.describe_snapshots(
            OwnerIds=['self'],
            Filters=[
                {'Name': 'tag:AutoDelete', 'Values': ['true']}
            ]
        )
        
        for snapshot in snapshots['Snapshots']:
            if snapshot['StartTime'].replace(tzinfo=None) < cutoff_date:
                ec2.delete_snapshot(SnapshotId=snapshot['SnapshotId'])
        
        # RDS 스냅샷
        db_snapshots = rds.describe_db_snapshots(
            DBInstanceIdentifier=db_instance_id,
            SnapshotType='manual'
        )
        
        for db_snapshot in db_snapshots['DBSnapshots']:
            if db_snapshot['SnapshotCreateTime'].replace(tzinfo=None) < cutoff_date:
                rds.delete_db_snapshot(
                    DBSnapshotIdentifier=db_snapshot['DBSnapshotIdentifier']
                )
        
        return {
            'statusCode': 200,
            'body': f'Backup completed: {timestamp}'
        }
        
    except Exception as e:
        print(f"Backup failed: {str(e)}")
        
        # SNS 알림
        sns = boto3.client('sns')
        sns.publish(
            TopicArn=os.environ['SNS_TOPIC_ARN'],
            Subject='Trading Bot Backup Failed',
            Message=f'Backup failed at {timestamp}\nError: {str(e)}'
        )
        
        raise