# Generated for HM Street Vendor billing upgrade

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0002_sale_delete_sales'),
    ]

    operations = [
        migrations.AddField(
            model_name='sale',
            name='bill_number',
            field=models.CharField(blank=True, max_length=20, unique=True, null=True),
        ),
        migrations.AddField(
            model_name='sale',
            name='order_type',
            field=models.CharField(
                choices=[
                    ('dine_in', 'Dine-in'),
                    ('takeaway', 'Takeaway'),
                    ('delivery', 'Home Delivery'),
                ],
                default='dine_in',
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='sale',
            name='customer_name',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='sale',
            name='customer_phone',
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name='sale',
            name='delivery_address',
            field=models.TextField(blank=True),
        ),
    ]
