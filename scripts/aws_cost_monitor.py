#!/usr/bin/env python3
"""
AWS Cost Monitoring Script
Tracks AWS usage and costs, sets up budgets and alarms
"""

import boto3
import json
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any

class AWSCostMonitor:
    """Monitor AWS costs and set up billing alarms."""
    
    def __init__(self, region: str = 'us-east-1'):
        self.region = region
        self.ce_client = boto3.client('ce', region_name=region)
        self.cloudwatch_client = boto3.client('cloudwatch', region_name=region)
        self.budgets_client = boto3.client('budgets', region_name=region)
        self.account_id = boto3.client('sts').get_caller_identity()['Account']
    
    def get_current_month_cost(self) -> Dict[str, Any]:
        """Get current month's cost."""
        start_date = datetime.now().replace(day=1).strftime('%Y-%m-%d')
        end_date = datetime.now().strftime('%Y-%m-%d')
        
        response = self.ce_client.get_cost_and_usage(
            TimePeriod={
                'Start': start_date,
                'End': end_date
            },
            Granularity='MONTHLY',
            Metrics=['BlendedCost', 'UnblendedCost']
        )
        
        if response['ResultsByTime']:
            result = response['ResultsByTime'][0]
            blended_cost = float(result['Total']['BlendedCost']['Amount'])
            
            return {
                'period': f"{start_date} to {end_date}",
                'blended_cost': round(blended_cost, 2),
                'currency': result['Total']['BlendedCost']['Unit']
            }
        
        return {'blended_cost': 0, 'currency': 'USD'}
    
    def get_service_breakdown(self) -> List[Dict[str, Any]]:
        """Get cost breakdown by service."""
        start_date = datetime.now().replace(day=1).strftime('%Y-%m-%d')
        end_date = datetime.now().strftime('%Y-%m-%d')
        
        response = self.ce_client.get_cost_and_usage(
            TimePeriod={
                'Start': start_date,
                'End': end_date
            },
            Granularity='MONTHLY',
            Metrics=['BlendedCost'],
            GroupBy=[
                {
                    'Type': 'DIMENSION',
                    'Key': 'SERVICE'
                }
            ]
        )
        
        services = []
        if response['ResultsByTime']:
            for group in response['ResultsByTime'][0]['Groups']:
                service_name = group['Keys'][0]
                cost = float(group['Metrics']['BlendedCost']['Amount'])
                
                if cost > 0:
                    services.append({
                        'service': service_name,
                        'cost': round(cost, 2)
                    })
        
        # Sort by cost descending
        services.sort(key=lambda x: x['cost'], reverse=True)
        return services
    
    def create_budget(self, budget_amount: float = 10.0) -> bool:
        """
        Create a monthly budget with alerts.
        
        Args:
            budget_amount: Monthly budget in USD
        """
        budget_name = "ECE461-Monthly-Budget"
        
        budget = {
            'BudgetName': budget_name,
            'BudgetLimit': {
                'Amount': str(budget_amount),
                'Unit': 'USD'
            },
            'TimeUnit': 'MONTHLY',
            'BudgetType': 'COST',
            'CostTypes': {
                'IncludeTax': True,
                'IncludeSubscription': True,
                'UseBlended': False,
                'IncludeRefund': False,
                'IncludeCredit': False,
                'IncludeUpfront': True,
                'IncludeRecurring': True,
                'IncludeOtherSubscription': True,
                'IncludeSupport': True,
                'IncludeDiscount': True,
                'UseAmortized': False
            }
        }
        
        # Create notifications for 50%, 80%, 100%
        notifications = [
            {
                'Notification': {
                    'NotificationType': 'ACTUAL',
                    'ComparisonOperator': 'GREATER_THAN',
                    'Threshold': 50.0,
                    'ThresholdType': 'PERCENTAGE'
                },
                'Subscribers': [
                    {
                        'SubscriptionType': 'EMAIL',
                        'Address': 'team17@example.com'  # Replace with actual email
                    }
                ]
            },
            {
                'Notification': {
                    'NotificationType': 'ACTUAL',
                    'ComparisonOperator': 'GREATER_THAN',
                    'Threshold': 80.0,
                    'ThresholdType': 'PERCENTAGE'
                },
                'Subscribers': [
                    {
                        'SubscriptionType': 'EMAIL',
                        'Address': 'team17@example.com'
                    }
                ]
            },
            {
                'Notification': {
                    'NotificationType': 'ACTUAL',
                    'ComparisonOperator': 'GREATER_THAN',
                    'Threshold': 100.0,
                    'ThresholdType': 'PERCENTAGE'
                },
                'Subscribers': [
                    {
                        'SubscriptionType': 'EMAIL',
                        'Address': 'team17@example.com'
                    }
                ]
            }
        ]
        
        try:
            # Check if budget exists
            try:
                self.budgets_client.describe_budget(
                    AccountId=self.account_id,
                    BudgetName=budget_name
                )
                print(f"Budget '{budget_name}' already exists. Updating...")
                
                self.budgets_client.update_budget(
                    AccountId=self.account_id,
                    NewBudget=budget
                )
            except self.budgets_client.exceptions.NotFoundException:
                print(f"Creating budget '{budget_name}'...")
                
                self.budgets_client.create_budget(
                    AccountId=self.account_id,
                    Budget=budget,
                    NotificationsWithSubscribers=notifications
                )
            
            print(f"✓ Budget created/updated: ${budget_amount}/month")
            return True
            
        except Exception as e:
            print(f"✗ Error creating budget: {e}")
            return False
    
    def create_billing_alarm(self, threshold: float = 10.0) -> bool:
        """
        Create CloudWatch billing alarm.
        
        Args:
            threshold: Dollar amount threshold
        """
        try:
            self.cloudwatch_client.put_metric_alarm(
                AlarmName='ECE461-Billing-Alarm',
                AlarmDescription=f'Alert when estimated charges exceed ${threshold}',
                ActionsEnabled=True,
                MetricName='EstimatedCharges',
                Namespace='AWS/Billing',
                Statistic='Maximum',
                Dimensions=[
                    {
                        'Name': 'Currency',
                        'Value': 'USD'
                    }
                ],
                Period=21600,  # 6 hours
                EvaluationPeriods=1,
                Threshold=threshold,
                ComparisonOperator='GreaterThanThreshold'
            )
            
            print(f"✓ Billing alarm created: ${threshold} threshold")
            return True
            
        except Exception as e:
            print(f"✗ Error creating billing alarm: {e}")
            return False
    
    def get_free_tier_usage(self) -> Dict[str, Any]:
        """
        Get free tier usage information.
        Note: This requires AWS Free Tier API which may not be available in all regions.
        """
        # Free tier limits (approximate)
        free_tier_limits = {
            'EC2': {
                'limit': 750,  # hours per month
                'unit': 'hours',
                'service': 't2.micro instances'
            },
            'RDS': {
                'limit': 750,
                'unit': 'hours',
                'service': 'db.t2.micro instances'
            },
            'S3': {
                'limit': 5,
                'unit': 'GB',
                'service': 'standard storage'
            },
            'Lambda': {
                'limit': 1000000,
                'unit': 'requests',
                'service': 'function invocations'
            }
        }
        
        return free_tier_limits
    
    def generate_cost_report(self) -> str:
        """Generate a comprehensive cost report."""
        print("=" * 70)
        print(" AWS COST MONITORING REPORT - ECE461 Team 17")
        print("=" * 70)
        print()
        
        # Current month cost
        print("📊 CURRENT MONTH COSTS")
        print("-" * 70)
        current_cost = self.get_current_month_cost()
        print(f"Period: {current_cost.get('period', 'N/A')}")
        print(f"Total Cost: ${current_cost.get('blended_cost', 0):.2f} {current_cost.get('currency', 'USD')}")
        print()
        
        # Service breakdown
        print("📦 SERVICE BREAKDOWN")
        print("-" * 70)
        services = self.get_service_breakdown()
        
        if services:
            for service in services[:10]:  # Top 10
                print(f"{service['service']:<40} ${service['cost']:>8.2f}")
        else:
            print("No cost data available yet.")
        print()
        
        # Free tier limits
        print("🆓 FREE TIER LIMITS")
        print("-" * 70)
        free_tier = self.get_free_tier_usage()
        for service, details in free_tier.items():
            print(f"{service:<15} {details['limit']:>10} {details['unit']:<10} ({details['service']})")
        print()
        
        # Recommendations
        print("💡 COST OPTIMIZATION RECOMMENDATIONS")
        print("-" * 70)
        total_cost = current_cost.get('blended_cost', 0)
        
        if total_cost > 0:
            print("✓ You are currently incurring costs")
            print("  - Review service breakdown above")
            print("  - Consider stopping unused EC2 instances")
            print("  - Enable S3 lifecycle policies for old objects")
        else:
            print("✓ You are within free tier limits")
        
        print("  - Set up budgets and alarms (see commands below)")
        print("  - Monitor usage regularly")
        print("  - Use AWS Cost Explorer for detailed analysis")
        print()
        
        # Action items
        print("🔧 RECOMMENDED ACTIONS")
        print("-" * 70)
        print("1. Create budget:")
        print("   python scripts/aws_cost_monitor.py --create-budget 10")
        print()
        print("2. Create billing alarm:")
        print("   python scripts/aws_cost_monitor.py --create-alarm 10")
        print()
        print("3. Stop EC2 instances when not in use:")
        print("   aws ec2 stop-instances --instance-ids i-xxxxx")
        print()
        
        print("=" * 70)
        
        return json.dumps({
            'current_cost': current_cost,
            'services': services,
            'timestamp': datetime.now().isoformat()
        }, indent=2)

def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='AWS Cost Monitoring Tool')
    parser.add_argument('--region', default='us-east-1', help='AWS region')
    parser.add_argument('--create-budget', type=float, metavar='AMOUNT', 
                       help='Create monthly budget with specified amount')
    parser.add_argument('--create-alarm', type=float, metavar='THRESHOLD',
                       help='Create billing alarm with specified threshold')
    parser.add_argument('--report', action='store_true', 
                       help='Generate cost report')
    parser.add_argument('--json', action='store_true',
                       help='Output in JSON format')
    
    args = parser.parse_args()
    
    monitor = AWSCostMonitor(region=args.region)
    
    # Generate report by default
    if not any([args.create_budget, args.create_alarm]):
        args.report = True
    
    if args.create_budget:
        monitor.create_budget(args.create_budget)
    
    if args.create_alarm:
        monitor.create_billing_alarm(args.create_alarm)
    
    if args.report:
        report_json = monitor.generate_cost_report()
        if args.json:
            print(report_json)

if __name__ == '__main__':
    main()





